package eu.kanade.tachiyomi.extension.all.pulsar

import okhttp3.CookieJar
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.ResponseBody.Companion.asResponseBody
import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.bitmap.Bitmap
import org.koitharu.kotatsu.parsers.config.ConfigKey
import org.koitharu.kotatsu.parsers.config.MangaSourceConfig
import org.koitharu.kotatsu.parsers.model.MangaSource as LibMangaSource

/**
 * Cihaz üstü kotatsu-parsers motoru için Pulsar konak sınıfı (Nyora örüntüsü):
 *
 *  - httpClient: host'un Mihon istemcisi + [RedirectDomainMapper] (pulsar
 *    tamir/öğrenme katmanı). Parser'ın kendi interceptor'ı (Site-Id/UA
 *    header'ları) CF çözücüsünün DIŞINA eklenir — Nyora'nın kanıtladığı gibi
 *    içine eklenirse WebView yanlış URL/header ile challenge çözer.
 *  - evaluateJs: WebView API'si yok → null (JS'li kaynaklar zarifçe düşer,
 *    HTTP/Jsoup kaynakları çalışır).
 *  - redrawImageResponse: karıştırılmış sayfa grid'lerini Android bitmap
 *    ile birleştirir.
 */
class PulsarContext(baseClient: OkHttpClient) : MangaLoaderContext() {

    @Volatile
    private var boundParser: Interceptor? = null

    fun bindParser(instance: Any?) {
        boundParser = unwrapDelegate(instance) as? Interceptor
    }

    private fun unwrapDelegate(instance: Any?): Any? {
        if (instance == null) return null
        return try {
            val f = instance.javaClass.getDeclaredField("delegate")
            f.isAccessible = true
            f.get(instance) ?: instance
        } catch (_: Throwable) {
            instance
        }
    }

    override val cookieJar: CookieJar = baseClient.cookieJar

    override val httpClient: OkHttpClient = baseClient.newBuilder()
        .followRedirects(true)
        .followSslRedirects(true)
        .apply {
            val chain = interceptors()
            val cfIndex = chain.indexOfLast { it.javaClass.name.contains("Cloudflare", ignoreCase = true) }
            val at = if (cfIndex >= 0) cfIndex else chain.size
            val parserInterceptor = Interceptor { c -> boundParser?.intercept(c) ?: c.proceed(c.request()) }
            chain.add(at, parserInterceptor)
            chain.add(at, RedirectDomainMapper)
        }
        .build()

    private val webViewUserAgent: String by lazy {
        runCatching {
            val app = Class.forName("android.app.ActivityThread")
                .getMethod("currentApplication").invoke(null) as android.content.Context
            if (android.os.Looper.myLooper() == android.os.Looper.getMainLooper()) {
                android.webkit.WebSettings.getDefaultUserAgent(app)
            } else {
                val holder = arrayOfNulls<String>(1)
                val latch = java.util.concurrent.CountDownLatch(1)
                android.os.Handler(android.os.Looper.getMainLooper()).post {
                    holder[0] = runCatching { android.webkit.WebSettings.getDefaultUserAgent(app) }.getOrNull()
                    latch.countDown()
                }
                latch.await(5, java.util.concurrent.TimeUnit.SECONDS)
                holder[0] ?: PULSAR_UA
            }
        }.getOrDefault(PULSAR_UA)
    }

    override fun getDefaultUserAgent(): String = webViewUserAgent

    override fun getConfig(source: LibMangaSource): MangaSourceConfig =
        PulsarSourceConfig(source, webViewUserAgent)

    @Deprecated("Provide a base url")
    override suspend fun evaluateJs(script: String): String? = null

    override suspend fun evaluateJs(baseUrl: String, script: String, timeout: Long): String? = null

    override fun redrawImageResponse(response: Response, redraw: (image: Bitmap) -> Bitmap): Response {
        val body = response.body ?: return response
        val decoded = body.byteStream().use { android.graphics.BitmapFactory.decodeStream(it) }
            ?: return response
        val redrawn = redraw(BitmapWrapper.create(decoded)) as BitmapWrapper
        val buffer = okio.Buffer()
        redrawn.use { it.compressTo(buffer.outputStream()) }
        val newBody = buffer.asResponseBody("image/jpeg".toMediaType())
        return response.newBuilder().body(newBody).build()
    }

    override fun createBitmap(width: Int, height: Int): Bitmap = BitmapWrapper.create(width, height)

    /**
     * ConfigKey.Domain'a patches.json'daki CANLI domaini verir (probe onarımı
     * ve alias'tan). Pin'leme ayrıca istek seviyesinde yapılır; parser bu
     * config'i görmezden gelse bile RedirectDomainMapper yakalar.
     */
    private class PulsarSourceConfig(
        private val source: LibMangaSource,
        private val userAgent: String,
    ) : MangaSourceConfig {
        @Suppress("UNCHECKED_CAST")
        override fun <T> get(key: ConfigKey<T>): T = when (key) {
            is ConfigKey.Domain -> {
                val override = PulsarPatches.DOMAIN_OVERRIDES[source.name]
                    ?: domainOverrideForHost(key.defaultValue)
                if (override != null) RedirectDomainMapper.pin(key.defaultValue, override)
                (override ?: key.defaultValue) as T
            }
            is ConfigKey.UserAgent -> userAgent as T
            else -> key.defaultValue
        }

        private fun domainOverrideForHost(host: String): String? {
            val bare = host.removePrefix("www.")
            return (PulsarPatches.DOMAIN_OVERRIDES.entries.firstOrNull { (k, v) ->
                k.equals(bare, true) || k.removePrefix("www.").equals(bare, true)
            })?.value
        }
    }

    private companion object {
        const val PULSAR_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
}
