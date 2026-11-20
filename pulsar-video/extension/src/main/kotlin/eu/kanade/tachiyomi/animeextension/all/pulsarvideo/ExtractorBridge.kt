package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import kotlin.coroutines.Continuation
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

/**
 * Kototoro'nun APK'sında gömülü olan CloudStream embed çözücülerini **çalışma anında**
 * çağırır. Kod kopyalanmaz (GPL bulaşmaz): yalnız host'un sınıf adı ve imzası kullanılır.
 *
 * Çözücü sınıfı `com.lagradost.cloudstream3.extractors.<Ad>` biçimindedir; imza:
 * `suspend fun getUrl(url: String, referer: String?, subtitleCallback: (SubtitleFile)->Unit,
 *                    callback: (ExtractorLink)->Unit)`
 *
 * Mihon'da bu sınıflar yoktur → [available] false döner, kaynak kendi ayrıştırıcısına düşer.
 */
internal object ExtractorBridge {

    private const val PKG = "com.lagradost.cloudstream3.extractors."

    /** Host APK'sında CloudStream çözücü katmanı var mı? */
    val available: Boolean by lazy {
        runCatching { Class.forName("com.lagradost.cloudstream3.utils.ExtractorApi") }.isSuccess
    }

    /** Senkron sarmalayıcı (videoListParse askıya alınamaz). */
    fun resolveBlocking(
        extractorName: String,
        url: String,
        referer: String? = null,
    ): List<Pair<String, String>> = runCatching {
        kotlinx.coroutines.runBlocking { resolve(extractorName, url, referer) }
    }.getOrDefault(emptyList())

    /**
     * Verilen çözücü adıyla (ör. "Videa", "GogoHelper") bağlantıyı çözer.
     * Dönen liste: (url, kalite etiketi).
     */
    suspend fun resolve(
        extractorName: String,
        url: String,
        referer: String? = null,
    ): List<Pair<String, String>> {
        if (!available) return emptyList()
        val links = mutableListOf<Pair<String, String>>()
        return runCatching {
            val cls = Class.forName(PKG + extractorName)
            val inst = cls.getDeclaredConstructor().newInstance()

            // ExtractorLink alanları: url + quality (getter'lar üzerinden okunur)
            val onLink: (Any) -> Unit = { link ->
                val u = runCatching { link.javaClass.getMethod("getUrl").invoke(link) as? String }.getOrNull()
                val q = runCatching { link.javaClass.getMethod("getQuality").invoke(link)?.toString() }
                    .getOrNull() ?: "auto"
                if (!u.isNullOrBlank()) links += u to q
                Unit
            }
            val onSub: (Any) -> Unit = { _ -> Unit }

            val m = cls.methods.firstOrNull { it.name == "getUrl" } ?: return emptyList()
            val cont = Continuation<Any?>(kotlin.coroutines.EmptyCoroutineContext) { }
            // Suspend fonksiyon: son parametre Continuation. Senkron dönerse Unit,
            // askıya alınırsa COROUTINE_SUSPENDED döner; çözücüler genelde senkron.
            val r = runCatching { m.invoke(inst, url, referer, onSub, onLink, cont) }
            if (r.isFailure) {
                // askıya alınmış olabilir: kısa bekleme ile callback'i topla
                Thread.sleep(1500)
            }
            links
        }.getOrDefault(emptyList())
    }
}
