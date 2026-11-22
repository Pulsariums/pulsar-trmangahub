package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import android.text.Html
import eu.kanade.tachiyomi.animesource.AnimeCatalogueSource
import eu.kanade.tachiyomi.animesource.model.AnimeFilterList
import eu.kanade.tachiyomi.animesource.model.AnimesPage
import eu.kanade.tachiyomi.animesource.model.Hoster
import eu.kanade.tachiyomi.animesource.model.SAnime
import eu.kanade.tachiyomi.animesource.model.SEpisode
import eu.kanade.tachiyomi.animesource.model.Video
import eu.kanade.tachiyomi.animesource.online.AnimeHttpSource
import okhttp3.Dns
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.SocketException
import java.net.UnknownHostException
import java.util.concurrent.ConcurrentHashMap
import javax.net.ssl.SSLException
import javax.net.ssl.SSLHandshakeException
import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Document

/**
 * Veri-güdümlü video kaynağı (Aniyomi `AnimeHttpSource`).
 *
 * DİKKAT: Bu sınıf iskelet. Aşama ayrıştırıcıları `config` alanından seçici okur;
 * config boşsa boş liste döner ve kaynak fabrikada hiç oluşturulmaz.
 * Adımlar: liste → detay → bölüm → video. Video üç biçimi destekler:
 *   1) doğrudan .m3u8/.mp4, 2) <iframe src> (embed), 3) JSON sources[].
 * Alan adları ölçüldükçe `video-catalogue.json`'a yazılır.
 */
class PulsarVideoSource(
    private val rawConfig: JSONObject,
    override val lang: String,
) : AnimeHttpSource() {

    private val config: JSONObject = rawConfig.optJSONObject("config") ?: JSONObject()

    override val name: String = rawConfig.optString("name", "Pulsar Video")
    override val baseUrl: String = rawConfig.optString("baseUrl", "").trimEnd('/')
    override val supportsLatest: Boolean = true

    private val ua: String = config.optString("userAgent", "").trim().ifBlank {
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }

    override fun headersBuilder() = super.headersBuilder()
        .set("User-Agent", ua)
        .set("Referer", "$baseUrl/")

    // ---- Liste -------------------------------------------------------------

    override fun popularAnimeRequest(page: Int): Request {
        val path = config.optString("listPath", "/")
        val url = if (path.startsWith("http")) path else "$baseUrl$path"
        return req(if (page > 1) "$url${if (url.contains('?')) '&' else '?'}page=$page" else url)
    }

    override fun popularAnimeParse(response: Response): AnimesPage {
        val doc = response.asJsoup()
        val sel = config.optString("itemSelector", "")
        if (sel.isBlank()) return AnimesPage(emptyList(), false)
        val items = doc.select(sel).mapNotNull { el ->
            val a = el.selectFirst("a[href]") ?: return@mapNotNull null
            SAnime.create().apply {
                setUrlWithoutDomain(a.absUrl("href").ifBlank { a.attr("href") })
                val titleAttr = config.optString("titleAttr", "")
                title = if (titleAttr.isNotBlank()) {
                    a.attr(titleAttr).ifBlank { el.attr(titleAttr) }
                } else {
                    el.selectFirst(config.optString("titleSelector", ""))?.text()
                        ?: a.text()
                }.ifBlank { "?" }
                thumbnail_url = el.selectFirst("img")?.let { img ->
                    img.absUrl("data-src").ifBlank { img.absUrl("src") }
                }
            }
        }
        return AnimesPage(items, items.isNotEmpty())
    }

    override fun latestUpdatesRequest(page: Int) = popularAnimeRequest(page)
    override fun latestUpdatesParse(response: Response) = popularAnimeParse(response)

    override fun searchAnimeRequest(page: Int, query: String, filters: AnimeFilterList): Request {
        val tpl = config.optString("searchUrl", "")
        if (tpl.isBlank()) throw Exception("Arama desteklenmiyor")
        val url = tpl.replace("{query}", query).replace("{page}", page.toString())
        return req(if (url.startsWith("http")) url else "$baseUrl$url")
    }

    override fun searchAnimeParse(response: Response) = popularAnimeParse(response)

    // ---- Detay ------------------------------------------------------------

    override fun animeDetailsRequest(anime: SAnime): Request = req(anime.url)

    override fun animeDetailsParse(response: Response): SAnime {
        val doc = response.asJsoup()
        return SAnime.create().apply {
            title = doc.selectFirst(config.optString("detailsTitleSelector", "h1"))?.text().orEmpty()
            description = doc.selectFirst(config.optString("detailsDescSelector", ""))?.text()
            genre = doc.select(config.optString("detailsGenreSelector", "")).joinToString(", ") { it.text() }
        }
    }

    // ---- Bölümler ---------------------------------------------------------

    override fun episodeListRequest(anime: SAnime): Request = req(anime.url)

    override fun episodeListParse(response: Response): List<SEpisode> {
        val doc = response.asJsoup()
        val sel = config.optString("episodeSelector", "")
        if (sel.isBlank()) return emptyList()
        return doc.select(sel).mapIndexedNotNull { idx, el ->
            val a = if (el.tagName() == "a") el else el.selectFirst("a[href]") ?: return@mapIndexedNotNull null
            SEpisode.create().apply {
                setUrlWithoutDomain(a.absUrl("href").ifBlank { a.attr("href") })
                name = config.optString("episodeNameAttr", "").let { attr ->
                    if (attr.isNotBlank()) el.attr(attr) else a.text()
                }.ifBlank { "Bölüm ${idx + 1}" }
                episode_number = Regex("(\\d+(?:\\.\\d+)?)").find(a.text())?.groupValues?.get(1)?.toFloatOrNull()
                    ?: (idx + 1).toFloat()
            }
        }.reversed()
    }

    // ---- Video: bölüm -> hoster listesi -> hoster başına video ----
    // Aniyomi v16 ABI'si hoster tabanlı çalışır:
    //   hosterListParse -> List<Hoster>, videoListParse(response, hoster) -> List<Video>

    override fun hosterListRequest(episode: SEpisode): Request = req(episode.url)

    override fun hosterListParse(response: Response): List<Hoster> {
        val doc = response.asJsoup()
        val sel = config.optString("hosterSelector", "")
        if (sel.isBlank()) return emptyList()
        // Bazı siteler hoster URL'sini href yerine bir nitelikte (ör. data-video)
        // ve Base64 gömülü olarak verir. hosterUrlAttr boşsa davranış eskisiyle
        // birebir aynı kalır: yalnız a[href] okunur.
        val urlAttr = config.optString("hosterUrlAttr", "").trim()
        val urlBase64 = config.opt("hosterUrlBase64").let { v ->
            when (v) {
                is Boolean -> v
                is Number -> v.toInt() == 1
                is String -> v.trim() == "1" || v.trim().equals("true", ignoreCase = true)
                else -> false
            }
        }
        return doc.select(sel).mapNotNull { el ->
            // URL kaynağı sırayla: (1) hosterUrlAttr, (2) <a href>, (3) <iframe src>,
            // (4) öğenin içindeki ilk a[href], yoksa ilk iframe[src].
            // 4. adım embed'in <a> ile verilmediği siteler (ör. animesuge) içindir.
            val target: org.jsoup.nodes.Element
            val rawUrl: String
            if (urlAttr.isNotBlank()) {
                val attrEl = if (el.hasAttr(urlAttr)) el else el.selectFirst("[$urlAttr]")
                    ?: return@mapNotNull null
                target = attrEl
                rawUrl = attrEl.attr(urlAttr)
            } else if (el.tagName() == "a") {
                target = el
                rawUrl = el.absUrl("href").ifBlank { el.attr("href") }
            } else if (el.tagName() == "iframe") {
                target = el
                rawUrl = iframeSrc(el)
            } else {
                val a = el.selectFirst("a[href]")
                if (a != null) {
                    target = a
                    rawUrl = a.absUrl("href").ifBlank { a.attr("href") }
                } else {
                    val iframe = el.selectFirst("iframe[src]") ?: return@mapNotNull null
                    target = iframe
                    rawUrl = iframeSrc(iframe)
                }
            }
            val url = if (urlBase64 && rawUrl.isNotBlank()) {
                decodeHosterUrl(rawUrl) ?: return@mapNotNull null
            } else {
                rawUrl
            }
            if (url.isBlank()) return@mapNotNull null
            val label = if (target.tagName() == "iframe") {
                target.attr("title").ifBlank { "embed" }
            } else {
                target.text().ifBlank { "embed" }
            }
            Hoster(url, label)
        }
    }

    /** iframe src'sini mutlaklaştırır; `absUrl` boşsa baseUrl'e göre çözer. */
    private fun iframeSrc(el: org.jsoup.nodes.Element): String {
        el.absUrl("src").takeIf { it.isNotBlank() }?.let { return it }
        val src = el.attr("src").trim()
        return when {
            src.startsWith("http://") || src.startsWith("https://") -> src
            src.startsWith("//") -> "https:$src"
            src.startsWith("/") -> "$baseUrl$src"
            src.isBlank() -> ""
            else -> "$baseUrl/$src"
        }
    }

    /** Base64 (standart veya URL-safe alfabe) hoster URL'sini çözer; dolguyu tamamlar. */
    private fun decodeHosterUrl(raw: String): String? {
        val normalized = raw.trim()
            .replace('-', '+')
            .replace('_', '/')
            .replace("\n", "")
            .replace("\r", "")
        if (normalized.isEmpty()) return null
        val padding = (4 - normalized.length % 4) % 4
        return runCatching {
            val bytes = android.util.Base64.decode(
                normalized + "=".repeat(padding),
                android.util.Base64.DEFAULT,
            )
            String(bytes, Charsets.UTF_8).trim()
        }.getOrNull()?.takeIf { it.isNotBlank() }
    }

    // Aniyomi v16 sezon listesi bekliyor; bu kaynaklarda sezon ayrimi yok.
    override fun seasonListParse(response: Response): List<SAnime> = emptyList()

    override fun videoListRequest(hoster: Hoster): Request = req(hoster.hosterUrl)

    override fun videoListParse(response: Response, hoster: Hoster): List<Video> {
        // 0) Host APK'sinda CloudStream cozucusu varsa onu kullan (Kototoro).
        val extractor = config.optString("hosterExtractor", "").trim()
        if (extractor.isNotBlank() && ExtractorBridge.available) {
            val links = ExtractorBridge.resolveBlocking(extractor, hoster.hosterUrl, "$baseUrl/")
            if (links.isNotEmpty()) return links.map { (u, q) -> Video(u, q) }
        }

        val body = response.body?.string().orEmpty()

        // 1) Doğrudan akış (m3u8/mp4)
        val direct = Regex("""(https?:[^\"'\s]+\.(?:m3u8|mp4)[^\"'\s]*)""").find(body)?.groupValues?.get(1)
        if (direct != null) return listOf(Video(direct, "auto"))

        // 2) iframe/embed
        val iframe = config.optString("videoSelector", "").takeIf { it.isNotBlank() }
            ?.let { Jsoup.parse(body).selectFirst(it)?.absUrl("src") }
        if (iframe != null) return listOf(Video(iframe, "embed"))

        // 3) JSON sources[]
        val jsonSel = config.optString("videoJsonSelector", "")
        if (jsonSel.isNotBlank()) {
            val jsonText = Jsoup.parse(body).selectFirst(jsonSel)?.html().orEmpty()
            val arr = runCatching { JSONObject(jsonText).optJSONArray("sources") }.getOrNull()
            if (arr != null) {
                return (0 until arr.length()).mapNotNull { k ->
                    val o = arr.optJSONObject(k) ?: return@mapNotNull null
                    val u = o.optString("file", o.optString("url", ""))
                    if (u.isBlank()) null else Video(u, o.optString("label", "auto"))
                }
            }
        }
        return emptyList()
    }

    // ---- Ag katmani: DPI/DNS engeli icin (manga motoruyla ayni desen) ----
    private val proxyUrl: String = config.optString("proxyUrl", "").trim()
    private val dohUrl: String = config.optString("dnsOverHttps", "").trim()
    private val tlsFragment: Boolean = config.optBoolean("tlsFragment", false)
    private val tlsFragmentSize: Int = config.optInt("tlsFragmentSize", 1).coerceIn(1, 64)

    // DoH yedegi (BILINCLI DAVRANIS DEGISIKLIGI): dnsOverHttps yazilmayan TUM
    // kaynaklarda da sistem DNS'i cozemezse sorgu varsayilan DoH ucuna
    // tekrarlanir; boylece her kaynaga ayar yazmak gerekmez. "off" yazilirsa
    // yedek tamamen kapanir (eski davranis: yalniz sistem DNS'i).
    private val dohFallbackEndpoint: String? =
        if (dohUrl.equals("off", ignoreCase = true)) {
            null
        } else {
            dohUrl.ifBlank { "https://cloudflare-dns.com/dns-query" }
        }

    // Ag katmani iki istemciye ayrilir:
    //  baseClient     : mevcut kurulum (proxy, DoH yedegi, ayarliysa tlsFragment).
    //  fragmentClient : ayni ayarlar + her zaman parcali ClientHello.
    // client = baseClient + TLS reset yakalayan interceptor; reset olursa istek
    // bir kez fragmentClient ile tekrarlanir. Boylece her kaynaga tlsFragment
    // yazmak gerekmez.
    private val baseClient: OkHttpClient by lazy {
        super.client.newBuilder()
            .apply {
                proxyFromConfig()?.let { proxy(it) }
                dohFallbackEndpoint?.let { dns(DohFallbackDns(it)) }
                if (tlsFragment) {
                    // DPI SNI'ya bakip baglantiyi kesiyorsa ClientHello'yu bol.
                    defaultTrustManager()?.let { tm ->
                        sslSocketFactory(TlsFragmentingSocketFactory(tlsFragmentSize), tm)
                    }
                }
            }
            .build()
    }

    /** baseClient ayarlarini kopyalar, ustune her zaman parcali TLS koyar. */
    private val fragmentClient: OkHttpClient by lazy {
        baseClient.newBuilder()
            .apply {
                defaultTrustManager()?.let { tm ->
                    sslSocketFactory(TlsFragmentingSocketFactory(tlsFragmentSize), tm)
                }
            }
            .build()
    }

    override val client: OkHttpClient by lazy {
        // tlsFragment zaten aciksa ilk istemci de parcalar; yedege gerek yok.
        if (tlsFragment) {
            baseClient
        } else {
            baseClient.newBuilder()
                .addInterceptor(TlsRetryInterceptor(fragmentClient))
                .build()
        }
    }

    /**
     * TLS el sikismasi DPI tarafindan sifirlandiginda istegi parcali ClientHello
     * gonderdigi icin gecen istemciyle bir kez tekrarlar. Parcalama da
     * basarisizsa ozgun istisna yukari firlatilir; cagiranin davranisi degismez.
     *
     * Sonsuz dongu korumasi: fragmentClient bu interceptor'i icermez; ayrica
     * X-Pulsar-Tls-Retry basligini tasiyan istek yeniden denenmez.
     */
    private class TlsRetryInterceptor(private val fragmentClient: OkHttpClient) : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val request = chain.request()
            try {
                return chain.proceed(request)
            } catch (e: IOException) {
                // Yalniz TLS/SNI kaynakli resetlerde yedege gec.
                if (!isTlsReset(e)) throw e
                // Bu istek zaten parcali denemeyle gonderildiyse tekrar etme.
                if (request.header(RETRY_HEADER) != null) throw e
                val retry = request.newBuilder()
                    .header(RETRY_HEADER, "1")
                    .build()
                return fragmentClient.newCall(retry).execute()
            }
        }

        /** Istisna zinciri TLS el sikismasi / baglanti sifirlama / sertifika izi tasiyor mu? */
        private fun isTlsReset(e: IOException): Boolean {
            var cur: Throwable? = e
            while (cur != null) {
                when (cur) {
                    is SSLHandshakeException -> return true
                    is SSLException -> return true
                    is java.security.cert.CertificateException -> return true
                    is SocketException -> {
                        val msg = cur.message.orEmpty().lowercase()
                        if (msg.contains("reset") || msg.contains("broken pipe")) return true
                    }
                }
                // Sertifika/trust-anchor hatasi SNI tabanli MITM'in isaretidir: araya
                // giren katman baglantiyi kendi sertifikasiyla keser, Android bunu
                // "Trust anchor for certification path not found" / CertPathValidator
                // olarak IOException seklinde dondurur. Parcali ClientHello ilk denemede
                // bunu engellemediginde yedege gecip tekrar denenir.
                val msg = cur.message.orEmpty().lowercase()
                if (msg.contains("trust anchor") ||
                    msg.contains("certpathvalidator") ||
                    msg.contains("certificate") ||
                    msg.contains("certpath")
                ) return true
                cur = cur.cause
            }
            return false
        }

        private companion object {
            const val RETRY_HEADER = "X-Pulsar-Tls-Retry"
        }
    }

    private fun proxyFromConfig(): Proxy? {
        if (proxyUrl.isBlank()) return null
        return try {
            val uri = java.net.URI(proxyUrl)
            val host = uri.host ?: return null
            val scheme = uri.scheme.orEmpty().lowercase()
            val port = if (uri.port > 0) uri.port else if (scheme.startsWith("socks")) 1080 else 8080
            val type = if (scheme.startsWith("socks")) Proxy.Type.SOCKS else Proxy.Type.HTTP
            Proxy(type, InetSocketAddress(host, port))
        } catch (_: Exception) {
            null
        }
    }

    private fun defaultTrustManager(): javax.net.ssl.X509TrustManager? = runCatching {
        val f = javax.net.ssl.TrustManagerFactory
            .getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm())
        f.init(null as java.security.KeyStore?)
        f.trustManagers.filterIsInstance<javax.net.ssl.X509TrustManager>().firstOrNull()
    }.getOrNull()

    /**
     * Once sistem DNS'i denenir (ek gecikme yok); cozulemezse sorgu DoH ile
     * tekrarlanir ve sonuc surec omru boyunca bellekte tutulur. DoH da
     * basarisizsa ozgun UnknownHostException firlatilir; boylece cagiran
     * tarafin hata davranisi degismez.
     *
     * Ayarli DoH kullanan kaynaklar da bu siniftan gecer: tek kod yolu.
     */
    private class DohFallbackDns(private val endpoint: String) : Dns {
        private val bootstrap = OkHttpClient()

        override fun lookup(hostname: String): List<InetAddress> {
            if (hostname == "localhost") return Dns.SYSTEM.lookup(hostname)

            var systemFailure: UnknownHostException? = null
            try {
                val system = Dns.SYSTEM.lookup(hostname)
                if (system.isNotEmpty()) return system
            } catch (e: UnknownHostException) {
                systemFailure = e
            }

            // Ayni host icin basarili DoH sonucu surec omru boyunca gecerlidir.
            CACHE[hostname]?.let { return it }

            val resolved = lookupDoh(hostname)
            if (resolved.isNotEmpty()) {
                CACHE[hostname] = resolved
                return resolved
            }
            // DoH da cozemedi: sistemin ozgun hatasini koru (bos sonucta uret).
            throw systemFailure ?: UnknownHostException(hostname)
        }

        /** DoH JSON yanitindan A kayitlarini okur; herhangi bir hata bos listedir. */
        private fun lookupDoh(hostname: String): List<InetAddress> = try {
            val url = endpoint.trimEnd('/') + "?name=" + hostname + "&type=A"
            val req = Request.Builder().url(url).header("Accept", "application/dns-json").build()
            bootstrap.newCall(req).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                Regex("\"data\"\\s*:\\s*\"([0-9.]+)\"")
                    .findAll(body)
                    .mapNotNull { m -> runCatching { InetAddress.getByName(m.groupValues[1]) }.getOrNull() }
                    .toList()
            }
        } catch (_: Exception) {
            emptyList()
        }

        private companion object {
            // Bellek ici onbellek: surec (eklenti sinif yukleyici) omru boyunca yasar.
            val CACHE = ConcurrentHashMap<String, List<InetAddress>>()
        }
    }

    private fun req(url: String): Request = Request.Builder()
        .url(if (url.startsWith("http")) url else "$baseUrl/${url.trimStart('/')}")
        .headers(headers)
        .build()

    private fun Response.asJsoup(): Document = Jsoup.parse(body?.string().orEmpty(), baseUrl)
}
