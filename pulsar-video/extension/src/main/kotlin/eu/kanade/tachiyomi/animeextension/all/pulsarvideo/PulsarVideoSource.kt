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
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.SocketException
import java.net.UnknownHostException
import java.net.URLEncoder
import java.util.concurrent.ConcurrentHashMap
import javax.net.ssl.SSLException
import javax.net.ssl.SSLHandshakeException
import org.json.JSONArray
import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

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

    /** Detay sayfasından tamamlanan kapaklar: içerik url'si -> kapak ("" = yok). */
    private val detailCoverCache = ConcurrentHashMap<String, String>()

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
        val items = parseItems(
            doc = response.asJsoup(),
            itemSelector = config.optString("itemSelector", ""),
            titleAttr = config.optString("titleAttr", ""),
            coverSelector = config.optString("coverSelector", ""),
        )
        enrichCoversFromDetails(items)
        return AnimesPage(items, items.isNotEmpty())
    }

    override fun latestUpdatesRequest(page: Int) = popularAnimeRequest(page)
    override fun latestUpdatesParse(response: Response) = popularAnimeParse(response)

    /**
     * Arama üç biçimi destekler:
     *  1) GET şablonu: `searchUrl` içinde `{query}` / `{page}`.
     *  2) POST formu: `searchMethod: "POST"` + `searchBody` ("keyword={query}").
     *  3) JSON yanıtı: `searchJsonTitle` doluysa gövde JSON dizisi/nesnesi olarak
     *     okunur (`searchJsonUrl` = bağlantı alanı, `searchJsonCover` = kapak alanı).
     * HTML sonuçlar `searchItemSelector`/`searchTitleAttr`/`searchCoverSelector`
     * ile ayrıştırılır; boş bırakılanlar liste seçicilerine düşer.
     */
    override fun searchAnimeRequest(page: Int, query: String, filters: AnimeFilterList): Request {
        val tpl = config.optString("searchUrl", "")
        if (tpl.isBlank()) throw Exception("Arama desteklenmiyor")
        val url = template(tpl, query, page).let { if (it.startsWith("http")) it else "$baseUrl$it" }
        if (config.optString("searchMethod", "GET").trim().uppercase() == "POST") {
            val body = template(
                config.optString("searchBody", "q={query}"),
                query,
                page,
                formEncoded = true,
            )
            return Request.Builder()
                .url(url)
                .headers(headers)
                .post(body.toRequestBody("application/x-www-form-urlencoded".toMediaTypeOrNull()))
                .build()
        }
        return req(url)
    }

    override fun searchAnimeParse(response: Response): AnimesPage {
        val jsonTitle = config.optString("searchJsonTitle", "").trim()
        if (jsonTitle.isNotEmpty()) return jsonSearchParse(response, jsonTitle)
        val items = parseItems(
            doc = response.asJsoup(),
            itemSelector = config.optString("searchItemSelector", "")
                .ifBlank { config.optString("itemSelector", "") },
            titleAttr = config.optString("searchTitleAttr", "")
                .ifBlank { config.optString("titleAttr", "") },
            coverSelector = config.optString("searchCoverSelector", "")
                .ifBlank { config.optString("coverSelector", "") },
        )
        return AnimesPage(items, items.isNotEmpty())
    }

    /** Ortak HTML liste ayrıştırıcısı; liste ve arama aynı kodu kullanır. */
    private fun parseItems(
        doc: Document,
        itemSelector: String,
        titleAttr: String,
        coverSelector: String,
    ): List<SAnime> {
        if (itemSelector.isBlank()) return emptyList()
        return doc.select(itemSelector).mapNotNull { el ->
            val a = el.selectFirst("a[href]") ?: return@mapNotNull null
            val href = a.absUrl("href").ifBlank { a.attr("href") }
            if (href.isBlank()) return@mapNotNull null
            SAnime.create().apply {
                setUrlWithoutDomain(href)
                title = if (titleAttr.isNotBlank()) {
                    a.attr(titleAttr).ifBlank { el.attr(titleAttr) }
                } else {
                    el.selectFirst(config.optString("titleSelector", ""))?.text()
                        ?: a.text()
                }.ifBlank { "?" }
                thumbnail_url = coverOf(el, coverSelector)
            }
        }
    }

    /** Kapak: `coverSelector` (boşsa ilk `img`), önce data-src sonra src. */
    private fun coverOf(el: Element, coverSelector: String): String? {
        val img = el.selectFirst(coverSelector.ifBlank { "img" }) ?: return null
        return img.absUrl("data-src").ifBlank { img.absUrl("src") }
            .ifBlank { img.attr("data-src").ifBlank { img.attr("src") } }
            .takeIf { it.isNotBlank() }
    }

    /**
     * JSON arama yanıtı (ör. AniWorld `/ajax/search` → `[{title, description, link}]`).
     * Kök dizi ya da `searchJsonArray` ile adlandırılmış dizi okunur; başlıktaki
     * HTML (`<em>Naruto</em>`) temizlenir.
     */
    private fun jsonSearchParse(response: Response, titleKey: String): AnimesPage {
        val text = response.body?.string().orEmpty().trim()
        val arr: JSONArray = runCatching {
            if (text.startsWith("[")) JSONArray(text) else JSONObject(text)
                .optJSONArray(config.optString("searchJsonArray", ""))
        }.getOrNull() ?: return AnimesPage(emptyList(), false)
        val urlKey = config.optString("searchJsonUrl", "link")
        val coverKey = config.optString("searchJsonCover", "").trim()
        val root = config.optString("searchJsonBaseUrl", "").ifBlank { baseUrl }
        val items = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val rawTitle = o.optString(titleKey, "").trim()
            val link = o.optString(urlKey, "").trim()
            if (rawTitle.isBlank() || link.isBlank()) return@mapNotNull null
            SAnime.create().apply {
                setUrlWithoutDomain(link)
                title = Jsoup.parse(rawTitle).text().trim().ifBlank { "?" }
                thumbnail_url = coverKey
                    .takeIf { it.isNotEmpty() }
                    ?.let { k -> o.optString(k, "").trim().takeIf { it.isNotEmpty() } }
                    ?.let { absolute(it, root) }
            }
        }
        return AnimesPage(items, items.isNotEmpty())
    }

    /**
     * Kapaksız liste kartları için detay sayfasından kapak tamamlar
     * (`coverFromDetail: true`). GogoAnime listesinde görsel yok; detayda
     * `og:image` var. İlk `coverEnrichLimit` kart için en fazla
     * `coverEnrichBudgetMs` süre harcanır, sonuç URL bazında önbelleklenir.
     */
    private fun enrichCoversFromDetails(items: List<SAnime>) {
        if (!config.optBoolean("coverFromDetail", false)) return
        val missing = items.filter { it.thumbnail_url.isNullOrBlank() }
        if (missing.isEmpty()) return
        val limit = config.optInt("coverEnrichLimit", 6).coerceIn(0, 20)
        if (limit == 0) return
        val budget = config.optInt("coverEnrichBudgetMs", 6_000).coerceIn(500, 20_000)
        val selector = config.optString("coverMetaSelector", "meta[property=og:image]")
        val deadline = System.currentTimeMillis() + budget
        var done = 0
        for (anime in missing) {
            if (done >= limit || System.currentTimeMillis() > deadline) break
            val cached = detailCoverCache[anime.url]
            if (cached != null) {
                if (cached.isNotBlank()) anime.thumbnail_url = cached
                done++
                continue
            }
            val cover = runCatching {
                client.newCall(req(anime.url)).execute().use { resp ->
                    if (!resp.isSuccessful) return@use ""
                    val el = Jsoup.parse(resp.body?.string().orEmpty(), baseUrl)
                        .selectFirst(selector) ?: return@use ""
                    el.attr("content").ifBlank { el.absUrl("src").ifBlank { el.attr("src") } }
                }
            }.getOrDefault("")
            if (detailCoverCache.size >= MAX_DETAIL_COVER_CACHE) detailCoverCache.clear()
            detailCoverCache[anime.url] = cover
            if (cover.isNotBlank()) anime.thumbnail_url = cover
            done++
        }
    }

    /** `{query}`/`{page}` yer tutucularını doldurur. */
    private fun template(
        tpl: String,
        query: String,
        page: Int,
        formEncoded: Boolean = false,
    ): String {
        val q = if (formEncoded) {
            runCatching { URLEncoder.encode(query, "UTF-8") }.getOrDefault(query)
        } else {
            query
        }
        return tpl.replace("{query}", q).replace("{page}", page.toString())
    }

    private fun absolute(value: String, root: String): String = when {
        value.startsWith("http://") || value.startsWith("https://") -> value
        value.startsWith("//") -> "https:$value"
        value.startsWith("/") -> root.trimEnd('/') + value
        else -> root.trimEnd('/') + "/" + value
    }

    // ---- Detay ------------------------------------------------------------

    override fun animeDetailsRequest(anime: SAnime): Request = req(anime.url)

    override fun animeDetailsParse(response: Response): SAnime {
        val doc = response.asJsoup()
        // Bos secici Jsoup'ta ValidationException ("String must not be empty")
        // firlatir; alanlar config'de yoksa sorgu hic calistirilmaz.
        val titleSel = config.optString("detailsTitleSelector", "h1").ifBlank { "h1" }
        val descSel = config.optString("detailsDescSelector", "").trim()
        val genreSel = config.optString("detailsGenreSelector", "").trim()
        return SAnime.create().apply {
            url = relativize(response.request.url.toString())
            title = doc.selectFirst(titleSel)?.text()?.trim().orEmpty()
                .ifBlank { doc.title().trim() }
                .ifBlank { response.request.url.pathSegments.lastOrNull { it.isNotBlank() }.orEmpty() }
                .ifBlank { "?" }
            description = descSel.takeIf { it.isNotEmpty() }?.let { doc.selectFirst(it)?.text() }
            genre = genreSel.takeIf { it.isNotEmpty() }
                ?.let { doc.select(it).joinToString(", ") { el -> el.text() } }
                .orEmpty()
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
            // Bos url hostta ayni ValidationException'i uretir: ogeyi atla.
            val rawUrl = a.absUrl("href").ifBlank { a.attr("href") }
            if (rawUrl.isBlank()) return@mapIndexedNotNull null
            SEpisode.create().apply {
                setUrlWithoutDomain(rawUrl)
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
    // Parca boyutlari ("1,2" gibi virgullu liste; en fazla 4 parca, 1-64 bayt).
    // BILINCLI DAVRANIS DEGISIKLIGI: tlsFragmentSizes yoksa varsayilan [1,2]'dir;
    // tek baytlik bolme bazi ara katmanlarda yeniden birlestiriliyordu.
    private val tlsFragmentSizes: IntArray =
        TlsFragmentingSocketFactory.parseFragmentSizes(config.optString("tlsFragmentSizes", ""))
    // Parcalar arasi taban gecikme (ms); 0 gecikmeyi kapatir.
    private val tlsFragmentDelay: Int = config
        .optInt("tlsFragmentDelay", TlsFragmentingSocketFactory.DEFAULT_FRAGMENT_DELAY_MS)
        .coerceIn(0, 100)

    // DoH yedegi (BILINCLI DAVRANIS DEGISIKLIGI): dnsOverHttps yazilmayan TUM
    // kaynaklarda da sistem DNS'i cozemezse sorgu varsayilan DoH ucuna
    // tekrarlanir; boylece her kaynaga ayar yazmak gerekmez. "off" yazilirsa
    // yedek tamamen kapanir (eski davranis: yalniz sistem DNS'i).
    private val dohFallbackEndpoint: String? =
        if (dohUrl.equals("off", ignoreCase = true)) {
            null
        } else {
            // DohFallbackDns uca cloudflare/dns.google/quad9 yedeklerini kendisi ekler.
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
                        sslSocketFactory(TlsFragmentingSocketFactory(tlsFragmentSizes, tlsFragmentDelay), tm)
                    }
                }
            }
            .build()
    }

    /**
     * baseClient ayarlarini kopyalar, ustune her zaman parcali TLS koyar.
     *
     * BILINCLI DAVRANIS DEGISIKLIGI: yedek istemci **DoH-oncelikli** DNS kullanir.
     * Engelli sitelerde ISP DNS'i NXDOMAIN yerine sahte/bayat bir IP dondurebiliyor;
     * bu durumda istek hicbir zaman DoH'a dusmuyor ve TLS "trust anchor" /
     * "connection reset" ile bitiyordu (cihaz raporu 2026-11-23: 15/18 18+ kaynak).
     * Ilk deneme (baseClient) sistem DNS'iyle hizli kalir; yalniz TLS hatasindan
     * sonraki yedek deneme DoH ile gercek IP'yi alir.
     */
    private val fragmentClient: OkHttpClient by lazy {
        baseClient.newBuilder()
            .apply {
                dohFallbackEndpoint?.let { dns(DohFallbackDns(it, preferDoh = true)) }
                defaultTrustManager()?.let { tm ->
                    sslSocketFactory(TlsFragmentingSocketFactory(tlsFragmentSizes, tlsFragmentDelay), tm)
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
    internal class TlsRetryInterceptor(private val fragmentClient: OkHttpClient) : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val request = chain.request()
            // Bu istek zaten parcali denemeyle gonderildiyse tekrar etme.
            if (request.header(RETRY_HEADER) != null) return chain.proceed(request)

            val retry = request.newBuilder()
                .header(RETRY_HEADER, "1")
                .build()
            val host = request.url.host

            // Bu host son 30 dk icinde TLS'te sifirlandiysa duz denemeyi atla:
            // her istekte iki deneme yapmak gecikme ve yuk getiriyordu.
            if (TlsFragmentSticky.isSticky(host)) {
                return fragmentClient.newCall(retry).execute()
            }

            try {
                return chain.proceed(request)
            } catch (e: IOException) {
                // Yalniz TLS/SNI kaynakli resetlerde yedege gec.
                if (!isTlsReset(e)) throw e
                TlsFragmentSticky.mark(host)
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
     * tekrarlanir. Uclar sirayla denenir (ayarli uc varsa o, sonra cloudflare,
     * dns.google, quad9); basarili sonuc 10 dk bellekte tutulur. DoH da
     * basarisizsa ozgun UnknownHostException firlatilir; boylece cagiran
     * tarafin hata davranisi degismez.
     *
     * Ayarli DoH kullanan kaynaklar da bu siniftan gecer: tek kod yolu.
     */
    internal class DohFallbackDns(
        configuredEndpoint: String? = null,
        private val preferDoh: Boolean = false,
    ) : Dns {
        private val bootstrap = OkHttpClient()
        private val endpoints: List<String> = buildEndpoints(configuredEndpoint)

        override fun lookup(hostname: String): List<InetAddress> {
            if (hostname == "localhost") return Dns.SYSTEM.lookup(hostname)

            // Yedek istemci: once DoH. ISP DNS'i sahte IP dondurse bile gercek
            // adres elde edilir; DoH uclarinin hepsi duserse sistem DNS'ine donulur.
            if (preferDoh) {
                CACHE[hostname]?.let { entry ->
                    if (entry.expiresAt > System.currentTimeMillis()) return entry.addresses
                    CACHE.remove(hostname)
                }
                val resolved = lookupDoh(hostname)
                if (resolved.isNotEmpty()) {
                    CACHE[hostname] = CacheEntry(resolved, System.currentTimeMillis() + CACHE_TTL_MS)
                    return resolved
                }
                return Dns.SYSTEM.lookup(hostname)
            }

            var systemFailure: UnknownHostException? = null
            try {
                val system = Dns.SYSTEM.lookup(hostname)
                if (system.isNotEmpty()) return system
            } catch (e: UnknownHostException) {
                systemFailure = e
            }

            // Basarili DoH sonucu 10 dk gecerlidir (TTL).
            CACHE[hostname]?.let { entry ->
                if (entry.expiresAt > System.currentTimeMillis()) return entry.addresses
                CACHE.remove(hostname)
            }

            val resolved = lookupDoh(hostname)
            if (resolved.isNotEmpty()) {
                CACHE[hostname] = CacheEntry(resolved, System.currentTimeMillis() + CACHE_TTL_MS)
                return resolved
            }
            // DoH da cozemedi: sistemin ozgun hatasini koru (bos sonucta uret).
            throw systemFailure ?: UnknownHostException(hostname)
        }

        /**
         * Uclari sirayla dener. Yanit basarisiz (HTTP 4xx/5xx), Status != 0
         * veya A kaydi yoksa sonraki uca gecilir; hepsi basarisizsa bos liste.
         */
        private fun lookupDoh(hostname: String): List<InetAddress> {
            for (endpoint in endpoints) {
                val result = queryEndpoint(endpoint, hostname)
                if (result.isNotEmpty()) return result
            }
            return emptyList()
        }

        private fun queryEndpoint(endpoint: String, hostname: String): List<InetAddress> = try {
            val url = endpoint.trimEnd('/') + "?name=" + hostname + "&type=A"
            val req = Request.Builder().url(url).header("Accept", "application/dns-json").build()
            bootstrap.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) {
                    emptyList()
                } else {
                    val body = resp.body?.string().orEmpty()
                    val status = STATUS.find(body)?.groupValues?.get(1)?.toIntOrNull()
                    // dns-json sozlesmesi: Status==0 basarili; alan yoksa govdeye guven.
                    if (status != null && status != 0) {
                        emptyList()
                    } else {
                        A_RECORD.findAll(body)
                            .mapNotNull { m ->
                                runCatching { InetAddress.getByName(m.groupValues[1]) }
                                    .getOrNull()
                            }
                            .filterIsInstance<java.net.Inet4Address>()
                            .toList()
                    }
                }
            }
        } catch (_: Exception) {
            emptyList()
        }

        private data class CacheEntry(val addresses: List<InetAddress>, val expiresAt: Long)

        private companion object {
            const val CACHE_TTL_MS = 10L * 60L * 1000L
            const val DEFAULT_CLOUDFLARE = "https://cloudflare-dns.com/dns-query"

            /** Siralama: ayarli uc (varsa), sonra cloudflare -> google -> quad9. */
            val DEFAULT_ENDPOINTS = listOf(
                DEFAULT_CLOUDFLARE,
                "https://dns.google/resolve",
                "https://dns.quad9.net:5053/dns-query",
            )

            fun buildEndpoints(configured: String?): List<String> {
                val list = ArrayList<String>()
                val configuredTrimmed = configured?.trim().orEmpty()
                if (configuredTrimmed.isNotEmpty()) list.add(configuredTrimmed)
                list.addAll(DEFAULT_ENDPOINTS)
                return list.distinct()
            }

            val A_RECORD = Regex("\"data\"\\s*:\\s*\"([0-9.]+)\"")
            val STATUS = Regex("\"Status\"\\s*:\\s*(\\d+)")

            // Bellek ici onbellek: surec (eklenti sinif yukleyici) omru boyunca yasar.
            val CACHE = ConcurrentHashMap<String, CacheEntry>()
        }
    }

    private companion object {
        /** Detaydan tamamlanan kapak önbelleğinin üst sınırı. */
        const val MAX_DETAIL_COVER_CACHE = 500
    }

    private fun req(url: String): Request = Request.Builder()
        .url(if (url.startsWith("http")) url else "$baseUrl/${url.trimStart('/')}")
        .headers(headers)
        .build()

    /** Ayni hosttaki mutlak URL'yi site-kokune gore goreli hale getirir. */
    private fun relativize(url: String): String {
        if (!url.startsWith("http")) return url
        val path = url.substringAfter("://").substringAfter('/', "")
        return if (hostOf(url) == hostOf(baseUrl)) "/$path" else url
    }

    private fun hostOf(u: String): String =
        u.substringAfter("://", u).substringBefore('/').removePrefix("www.").lowercase()

    private fun Response.asJsoup(): Document = Jsoup.parse(body?.string().orEmpty(), baseUrl)
}
