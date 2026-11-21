package eu.kanade.tachiyomi.extension.all.pulsar

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.HttpSource
import okhttp3.Dns
import okhttp3.Headers
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.concurrent.TimeUnit

class PulsarSource(
    private val rawConfig: JSONObject,
    override val lang: String
) : HttpSource() {

    override val name: String = rawConfig.optString("name", "Unknown Source")
    override val baseUrl: String = rawConfig.optString("baseUrl", "").trimEnd('/')
    val domain: String = rawConfig.optString("domain", "")
    val engine: String = rawConfig.optString("engine", "custom")
    val config: JSONObject = rawConfig.optJSONObject("config") ?: JSONObject()

    // Kototoro'nun varsayılan (mobil WebView) UA'sını kaldırıp tek masaüstü UA bırakıyoruz;
    // iki User-Agent başlığı bazı CDN'lerde 403'e yol açıyor.
    private val defaultUserAgent: String =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    // Kaynak ayarinda "userAgent" verilmisse onu kullaniyoruz: Cloudflare cerezi
    // (cf_clearance) tarayicinin kendi UA'si ile eslesmedigi surece gecerli olmuyor.
    private val desktopUserAgent: String =
        config.optString("userAgent", "").trim().ifBlank { defaultUserAgent }

    // Tarayicidan alinan ham cerez dizesi ("cf_clearance=...; __cf_bm=...").
    private val cookieHeader: String = config.optString("cookie", "").trim()

    // ISP DPI/DNS engeli icin kaynak basina ag ayarlari:
    //  proxyUrl      : "http://host:port" veya "socks5://host:port"
    //  dnsOverHttps  : DoH ucu, or. "https://cloudflare-dns.com/dns-query"
    private val proxyUrl: String = config.optString("proxyUrl", "").trim()
    private val dohUrl: String = config.optString("dnsOverHttps", "").trim()
    // SNI/DPI atlatma: TLS ClientHello'yu parcalayarak gonder (VPN degil).
    private val tlsFragment: Boolean = config.optBoolean("tlsFragment", false)
    private val tlsFragmentSize: Int = config.optInt("tlsFragmentSize", 1).coerceIn(1, 64)

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

    /** Host'un kendi guven zincirini kullan (sistem CA deposu). */
    private fun defaultTrustManager(): javax.net.ssl.X509TrustManager? = runCatching {
        val f = javax.net.ssl.TrustManagerFactory
            .getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm())
        f.init(null as java.security.KeyStore?)
        f.trustManagers.filterIsInstance<javax.net.ssl.X509TrustManager>().firstOrNull()
    }.getOrNull()

    /** DoH ile A kaydi cozer; uç hata verirse sistem DNS'ine duser. */
    private class DohDns(private val endpoint: String) : Dns {
        private val bootstrap = OkHttpClient()
        private val fallback = Dns.SYSTEM

        override fun lookup(hostname: String): List<InetAddress> {
            if (hostname == "localhost") return fallback.lookup(hostname)
            return try {
                val url = endpoint.trimEnd('/') + "?name=" + hostname + "&type=A"
                val req = Request.Builder().url(url).header("Accept", "application/dns-json").build()
                bootstrap.newCall(req).execute().use { resp ->
                    val body = resp.body?.string().orEmpty()
                    val ips = Regex("\"data\"\\s*:\\s*\"([0-9.]+)\"")
                        .findAll(body)
                        .mapNotNull { m -> runCatching { InetAddress.getByName(m.groupValues[1]) }.getOrNull() }
                        .toList()
                    if (ips.isNotEmpty()) ips else fallback.lookup(hostname)
                }
            } catch (_: Exception) {
                fallback.lookup(hostname)
            }
        }
    }

    override val supportsLatest: Boolean = true

    override val client: OkHttpClient by lazy {
        network.client.newBuilder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .followRedirects(true)
            .apply {
                // DPI/proxy: yalniz bu kaynak icin gecerli, digerlerini etkilemez.
                proxyFromConfig()?.let { proxy(it) }
                if (dohUrl.isNotBlank()) dns(DohDns(dohUrl))
                if (tlsFragment) {
                    // DPI SNI'ya bakip baglantiyi kesiyorsa ClientHello'yu bol.
                    defaultTrustManager()?.let { tm ->
                        sslSocketFactory(TlsFragmentingSocketFactory(tlsFragmentSize), tm)
                    }
                }
            }
            .apply { if (config.optBoolean("http1", false)) protocols(listOf(Protocol.HTTP_1_1)) }
            // Aralıklı 403 (Amanga CDN): GET için 5 deneme; HTTP/2 akış sıfırlaması
            // (Kuroi PROTOCOL_ERROR) gibi IOException için 2 deneme.
            .addInterceptor { chain ->
                val request = chain.request()
                val idempotent = request.method == "GET"
                var attempt = 0
                var result: Response? = null
                while (result == null) {
                    try {
                        val r = chain.proceed(request)
                        if (idempotent && r.code == 403 && attempt < 5) {
                            r.close()
                            attempt++
                            Thread.sleep(250L * attempt + (0..150).random())
                        } else {
                            result = r
                        }
                    } catch (e: java.io.IOException) {
                        if (!idempotent || attempt >= 2 || e is java.net.SocketTimeoutException) throw e
                        attempt++
                        Thread.sleep(300L * attempt)
                    }
                }
                checkNotNull(result)
            }
            .build()
    }

    // Mihon eklentileri kaynak başına başlık gönderebilir (Referer/Cookie/UA).
    // catalogue.json'da "headers": {"Referer": "...", "Cookie": "..."} ile verilir.
    override fun headersBuilder(): Headers.Builder {
        val b = super.headersBuilder()
            .removeAll("User-Agent")
            .add("Referer", "$baseUrl/")
            .add("User-Agent", desktopUserAgent)
        var cookieFromHeaders = false
        config.optJSONObject("headers")?.let { o ->
            for (k in o.keys()) {
                val v = o.optString(k)
                if (v.isBlank()) continue
                b.set(k, v)
                if (k.equals("Cookie", ignoreCase = true)) cookieFromHeaders = true
            }
        }
        // headers nesnesindeki Cookie oncelikli; yoksa config.cookie uygulanir.
        if (!cookieFromHeaders && cookieHeader.isNotBlank()) b.set("Cookie", cookieHeader)
        return b
    }

    override val id: Long by lazy {
        val key = "pulsar/${domain.removePrefix("www.")}/$lang"
        var h = 1125899906842597L
        for (ch in key) h = 31 * h + ch.code
        h and Long.MAX_VALUE
    }

    // Popular Manga
    override fun popularMangaRequest(page: Int): Request {
        // Bazı siteler listeyi HTML yerine JSON API'de veriyor (mangadiyari, mangawt).
        val listJsonUrl = config.optString("listJsonUrl", "")
        if (listJsonUrl.isNotBlank()) {
            val target = absolute(listJsonUrl.replace("{page}", page.toString()))
            return Request.Builder().url(target).headers(headers).build()
        }
        val listPath = config.optString("listPath", "/manga").trimStart('/')
        val url = if (page > 1) "$baseUrl/$listPath?page=$page" else "$baseUrl/$listPath"
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun popularMangaParse(response: Response): MangasPage {
        if (config.optString("listJsonUrl", "").isNotBlank()) {
            return jsonListParse(response)
        }
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val itemSelector = config.optString("itemSelector", "")
        val excl = config.optString("listExcludeUrl", "")
        val exclRe = if (excl.isBlank()) null else runCatching { Regex(excl) }.getOrNull()
        val items = EngineRegistry.parseList(doc, itemSelector, baseUrl)
            .ifEmpty { EngineRegistry.rscList(html, baseUrl) }
            .filter { exclRe == null || !exclRe.containsMatchIn(it.url) }

        val mangas = items.map { item ->
            SManga.create().apply {
                url = relativize(item.url)
                title = item.title
                thumbnail_url = realImageUrl(item.coverUrl)
            }
        }
        return MangasPage(mangas, hasNextPage = mangas.size >= 10)
    }

    // JSON liste: config'teki alan adlarıyla eşlenir; url'ler GÖRELİ üretilir.
    private fun jsonListParse(response: Response): MangasPage {
        val text = response.body?.string().orEmpty()
        val root = runCatching { JSONObject(text) }.getOrNull()
        val itemsKey = config.optString("listJsonItems", "")
        // Alan yolu boş kaldığında kök dizi öğe listesidir: /wp-json/wp/v2/comic gibi
        // uçlar gövdeyi doğrudan [ ... ] döndürüyor (vixenlogic). JSONObject yolu aynen durur.
        // listJsonItems düz anahtar da olabilir yol da ("data.latest", "props.paginate.data").
        val arr = (if (root != null) {
            EngineRegistry.jsonPath(root, itemsKey.ifBlank { "data" })
        } else {
            null
        }) as? JSONArray
            ?: runCatching { JSONArray(text.trim()) }.getOrNull()
            ?: return MangasPage(emptyList(), hasNextPage = false)
        val titleKey = config.optString("listJsonTitle", "title")
        val slugKey = config.optString("listJsonUrlField", "slug")
        val template = config.optString("listJsonUrlTemplate", "")
        val coverKey = config.optString("listJsonCover", "")
        val mangas = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val slug = jsonField(o, slugKey).trim()
            if (slug.isEmpty() || template.isBlank()) return@mapNotNull null
            SManga.create().apply {
                url = template.replace("{slug}", slug)
                title = jsonField(o, titleKey).trim()
                thumbnail_url = if (coverKey.isBlank()) null else realImageUrl(jsonField(o, coverKey))
            }
        }
        return MangasPage(mangas, hasNextPage = mangas.size >= 10)
    }

    // Latest Updates
    override fun latestUpdatesRequest(page: Int): Request = popularMangaRequest(page)
    override fun latestUpdatesParse(response: Response): MangasPage = popularMangaParse(response)

    // Search
    // Arama çoğu sitede ?s= ile çalışır; Madara/WordPress sitelerinde arama
    // admin-ajax.php üzerinden POST gövdesiyle döner (ör. ruyamanga2.com:
    // action=wp-manga-search-manga, gövde title=one). Bu yüzden adres ve yöntem
    // catalogue.json'dan gelir.
    // Desteklenmeyen/kisa sorgu istisnasi (IllegalArgumentException) aramayi
    // dusurmesin: Mihon'da bu durumda bos sonuc beklenir (ComicK, HoneyManga).
    override suspend fun getSearchManga(page: Int, query: String, filters: FilterList): MangasPage =
        runCatching { super.getSearchManga(page, query, filters) }.getOrElse { e ->
            if (e is IllegalArgumentException) MangasPage(emptyList(), hasNextPage = false) else throw e
        }
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val apiUrl = config.optString("searchUrl", "")
        if (apiUrl.isBlank()) {
            return Request.Builder().url("$baseUrl/?s=$query").headers(headers).build()
        }
        val isPost = config.optString("searchMethod", "GET").equals("POST", ignoreCase = true)
        if (!isPost) {
            val target = absolute(apiUrl.replace("{query}", query))
            return Request.Builder().url(target).headers(headers).build()
        }
        val target = absolute(if (page > 1) "$apiUrl&page=$page" else apiUrl)
        val body = config.optString("searchBody", "title={query}").replace("{query}", query)
        return Request.Builder()
            .url(target)
            .headers(headers)
            .post(body.toRequestBody("application/x-www-form-urlencoded; charset=UTF-8".toMediaType()))
            .build()
    }

    override fun searchMangaParse(response: Response): MangasPage {
        val arrayKey = config.optString("searchJsonItems", "")
        if (arrayKey.isBlank()) return popularMangaParse(response)
        val text = response.body?.string().orEmpty()
        // searchJsonItems düz anahtar ya da yol olabilir ("hits", "data.results",
        // "data.items[0].list"). Kök dizi cevabı da kabul edilir.
        val root = runCatching { JSONObject(text) }.getOrNull()
        val arr = (if (root != null) EngineRegistry.jsonPath(root, arrayKey) else null) as? JSONArray
            ?: runCatching { JSONArray(text.trim()) }.getOrNull()
            ?: return MangasPage(emptyList(), hasNextPage = false)
        val urlKey = config.optString("searchJsonUrl", "url")
        val titleKey = config.optString("searchJsonTitle", "title")
        val mangas = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val raw = jsonField(o, urlKey).trim()
            if (raw.isEmpty()) return@mapNotNull null
            val prefix = config.optString("searchJsonPathPrefix", "")
            val u = if (prefix.isNotEmpty() && !raw.startsWith("http") && !raw.startsWith("/")) {
                prefix.trimEnd('/') + "/" + raw.trimStart('/')
            } else {
                raw
            }
            SManga.create().apply {
                url = relativize(u)
                title = jsonField(o, titleKey).trim()
            }
        }
        return MangasPage(mangas, hasNextPage = false)
    }

    // Kototoro ve Mihon istek kurarken baseUrl + manga.url yapar. Mutlak URL
    // verilirse host "site.comhttps" olur (cihaz: www.amangaplanet.com.trhttps).
    // Bu yüzden SManga/SChapter url'i GÖRELİ tutulur; farklı host (CDN) olduğu
    // gibi bırakılır.
    private fun hostOf(u: String): String =
        u.substringAfter("://", u).substringBefore('/').removePrefix("www.").lowercase()

    // Slept Manga kapakları /api/image-proxy?url=<CDN adresi> biçiminde geliyor ve
    // proxy 403 dönüyor ("API Access Denied"); CDN adresinin kendisi Referer'la 200.
    // Bu yüzden proxy adresini çözüp doğrudan CDN'i kullanıyoruz.
    private fun realImageUrl(raw: String?): String? {
        val u = raw?.trim().orEmpty()
        if (u.isEmpty()) return null
        val abs = absolute(u)
        if (!abs.contains("image-proxy")) return abs
        val enc = abs.substringAfter("url=", "").substringBefore('&')
        if (enc.isEmpty()) return abs
        val decoded = runCatching {
            java.net.URLDecoder.decode(enc.replace("+", "%2B"), "UTF-8")
        }.getOrNull()
        return if (decoded != null && decoded.startsWith("http")) decoded else abs
    }

    private fun relativize(url: String): String {
        if (!url.startsWith("http")) return url
        val path = url.substringAfter("://").substringAfter('/', "")
        return if (hostOf(url) == hostOf(baseUrl)) "/" + path else url
    }

    // Config alanı düz anahtar da olabilir JSON yolu da ("data.latest",
    // "hits[].document.slug", "items[0].url"). Yolda '.'/'[' yoksa eski
    // optString davranışı aynen işler; yol varsa EngineRegistry.jsonPath çözer.
    private fun jsonField(o: Any?, key: String): String {
        val k = key.trim()
        if (k.isEmpty()) return ""
        if (!k.contains('.') && !k.contains('[')) {
            return (o as? JSONObject)?.optString(k) ?: ""
        }
        return when (val v = EngineRegistry.jsonPath(o, k)) {
            null, is JSONObject, is JSONArray -> ""
            else -> v.toString()
        }
    }

    // ---- URL birleştirme -------------------------------------------------
    // EngineRegistry MUTLAK URL üretir (https://site/manga/x). HttpSource ise
    // istek kurarken baseUrl + manga.url yapar; ikisi birleşince host
    // "site.comhttps" oluyordu. Cihaz raporu: Unable to resolve host
    // "anikiga.comhttps" — Amanga Planet, Anikiga, Rüya Manga bu yüzden düştü.
    // Ayar dosyasindaki yollar goreli olabilir (searchUrl=/?s={query}, /search?q=...).
    // OkHttp sema ister; goreli adres "Expected URL scheme 'http' or 'https'"
    // firlatiyordu (cihaz: Comizy, GedeComix, PatiManga, Tilki Scans).
    private fun absolute(url: String): String {
        val t = url.trim()
        if (t.startsWith("http://") || t.startsWith("https://")) return secure(t)
        if (t.startsWith("//")) return (if (baseUrl.startsWith("https://")) "https:" else "http:") + t
        return "$baseUrl/${t.trimStart('/')}"
    }

    // Site https iken bazı Madara temaları bölüm/görsel linklerini http:// yazıyor;
    // sunucu http bağlantısını kesiyor ("unexpected end of stream on http://...").
    // http linkini https'e yükseltiyoruz (manga18free, manhwaclub, manga18x -> manhwaclub.net).
    private fun secure(url: String): String {
        if (!url.startsWith("http://") || !baseUrl.startsWith("https://")) return url
        return "https://" + url.removePrefix("http://")
    }

    override fun mangaDetailsRequest(manga: SManga): Request =
        Request.Builder().url(absolute(manga.url)).headers(headers).build()

    // Bölümler sayfada <a> olarak yoksa, JSON API'den geliyorsa (mangaball.com):
    // chapterApiUrl şablonu {id} ve {page} yer tutucularını taşır, id manga
    // adresinden chapterApiIdPattern ile çıkarılır. Ayar boşsa eski yol işler.
    private fun apiChapterUrl(manga: SManga): String? {
        val template = config.optString("chapterApiUrl", "")
        if (template.isBlank()) return null
        val pattern = config.optString("chapterApiIdPattern", "")
        if (pattern.isBlank()) return null
        val id = runCatching { Regex(pattern).find(manga.url)?.groupValues?.getOrNull(1) }
            .getOrNull().orEmpty()
        if (id.isEmpty()) return null
        return template.replace("{id}", id).replace("{page}", "1")
    }

    private fun apiChapters(response: Response): List<SChapter> {
        val text = response.body?.string().orEmpty()
        val itemsKey = config.optString("chapterApiItems", "data")
        // chapterApiItems düz anahtar ya da yol olabilir: "data.chapters",
        // "data.items[0].chapters". Gövde kök dizi ise alan yolu uygulanmaz,
        // dizinin kendisi bölüm listesidir.
        val rootObj = runCatching { JSONObject(text) }.getOrNull()
        val arr = (if (rootObj != null) EngineRegistry.jsonPath(rootObj, itemsKey) else null) as? JSONArray
            ?: runCatching { JSONArray(text.trim()) }.getOrNull()
            ?: return emptyList()
        val nameKey = config.optString("chapterApiFieldName", "name")
        val numKey = config.optString("chapterApiFieldNumber", "number")
        val urlKey = config.optString("chapterApiFieldUrl", "url")
        // url alanı yoksa şablon: {id} = API adresinin son yol parçası, {value} = numKey değeri (lunarx).
        val urlTemplate = config.optString("chapterApiUrlTemplate", "")
        val preferLang = config.optString("chapterApiPreferLang", "")
        val apiId = response.request.url.encodedPath.trimEnd('/').substringAfterLast('/')
        val byUrl = LinkedHashMap<String, SChapter>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val raw = if (urlTemplate.isNotBlank()) {
                val v = jsonField(o, numKey).trim()
                if (v.isEmpty()) "" else urlTemplate.replace("{id}", apiId).replace("{value}", v)
            } else {
                jsonField(o, urlKey).trim()
            }
            if (raw.isEmpty()) continue
            val num = jsonField(o, numKey).replace(',', '.').toFloatOrNull() ?: 0f
            val numText = if (num % 1f == 0f) num.toInt().toString() else num.toString()
            val title = (if (urlTemplate.isBlank()) jsonField(o, nameKey).trim() else "")
                .ifBlank { "Bölüm $numText" }
            val ch = SChapter.create().apply {
                url = relativize(raw)
                name = title
                chapter_number = num
                date_upload = 0L
            }
            // Aynı bölüm birden çok dilde gelebilir: tercih edilen dil kazanır.
            val exists = byUrl.containsKey(ch.url)
            if (!exists || (preferLang.isNotBlank() && o.optString("language") == preferLang)) {
                byUrl[ch.url] = ch
            }
        }
        return byUrl.values.toList()
    }

    override fun chapterListRequest(manga: SManga): Request {
        val api = apiChapterUrl(manga)
        if (api != null) return Request.Builder().url(absolute(api)).headers(headers).build()
        val mangaUrl = absolute(manga.url)
        // Madara: bölümler sayfada değil POST {manga}/ajax/chapters/ yanıtında (anikiga).
        if (config.optBoolean("chapterAjax", false)) {
            return Request.Builder()
                .url(mangaUrl.trimEnd('/') + "/ajax/chapters/")
                .headers(headers.newBuilder().set("X-Requested-With", "XMLHttpRequest").set("Referer", mangaUrl).build())
                .post(okhttp3.FormBody.Builder().build())
                .build()
        }
        return Request.Builder().url(mangaUrl).headers(headers).build()
    }

    // Sayfa listesi bölüm HTML'inde değil ayrı JSON API'de olabilir (lunarx).
    // pageApiUrl şablonundaki {1},{2}... yakalama gruplarıyla doldurulur.
    private fun apiPageUrl(chapter: SChapter): String? {
        val template = config.optString("pageApiUrl", "")
        if (template.isBlank()) return null
        val lookup = lookupApiId(chapter)
        if (lookup != null) return template.replace("{1}", lookup).takeIf { !it.contains("{") }
        val pattern = config.optString("pageApiIdPattern", "")
        if (pattern.isBlank()) return null
        val m = runCatching { Regex(pattern).find(chapter.url) }.getOrNull() ?: return null
        var url = template
        for (i in 1 until m.groupValues.size) url = url.replace("{$i}", m.groupValues[i])
        return url.takeIf { !it.contains("{") }
    }

    // pageApiMethod "POST" iken gövde şablonu: {url} bölüm adresi, {1},{2}... yakalama grupları.
    private fun fillApiBody(chapter: SChapter, template: String): String {
        var body = template.replace("{url}", absolute(chapter.url))
        val pattern = config.optString("pageApiIdPattern", "")
        if (pattern.isNotBlank()) {
            val m = runCatching { Regex(pattern).find(chapter.url) }.getOrNull()
            if (m != null) for (i in 1 until m.groupValues.size) body = body.replace("{$i}", m.groupValues[i])
        }
        return body
    }

    // Bölüm URL'sindeki sayı gerçek id değilse: seri JSON'undaki numara alanından id çözülür.
    // Örn. /seri/<slug>/bolum/3851 -> /api/series/<slug> -> chapter_number=3851 -> id=6417.
    private fun lookupApiId(chapter: SChapter): String? {
        val lookupTemplate = config.optString("pageApiLookupUrl", "")
        val lookupPattern = config.optString("pageApiLookupPattern", "")
        if (lookupTemplate.isBlank() || lookupPattern.isBlank()) return null
        val m = runCatching { Regex(lookupPattern).find(chapter.url) }.getOrNull() ?: return null
        if (m.groupValues.size < 2) return null
        var url = lookupTemplate
        for (i in 1 until m.groupValues.size) url = url.replace("{$i}", m.groupValues[i])
        if (url.contains("{")) return null
        val text = runCatching {
            client.newCall(Request.Builder().url(absolute(url)).headers(headers).build())
                .execute().use { it.body?.string().orEmpty() }
        }.getOrNull().orEmpty()
        val root = runCatching { JSONObject(text) }.getOrNull() ?: return null
        var node: Any? = root
        for (part in config.optString("pageApiLookupItems", "chapters").split('.')) {
            node = (node as? JSONObject)?.opt(part)
        }
        val arr = node as? org.json.JSONArray ?: return null
        val numberField = config.optString("pageApiLookupNumberField", "chapter_number")
        val idField = config.optString("pageApiLookupIdField", "id")
        val wanted = m.groupValues.last().toDoubleOrNull() ?: return null
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val n = o.optString(numberField).toDoubleOrNull() ?: continue
            if (n == wanted) return o.optString(idField).takeIf { it.isNotBlank() }
        }
        return null
    }

    private fun apiPages(response: Response): List<Page> {
        val text = response.body?.string().orEmpty()
        val root = runCatching { JSONObject(text) }.getOrNull()
        // Gövde kök dizi olabilir (mimihentai items[] yerine doğrudan liste):
        // o zaman alan yolu uygulanmaz, dizinin kendisi sayfa listesidir.
        val rootArr = if (root == null) runCatching { JSONArray(text.trim()) }.getOrNull() else null
        if (root == null && rootArr == null) {
            throw IllegalStateException(
                "TANI4 api url=${response.request.url} len=${text.length} ilk=${text.take(160)}",
            )
        }
        // pageApiItems düz anahtar ya da yol olabilir: "data.images",
        // "props.paginate.data", "chapters[].images".
        val arr = (if (root != null) {
            EngineRegistry.jsonPath(root, config.optString("pageApiItems", "images"))
        } else {
            null
        }) as? org.json.JSONArray
            ?: rootArr
            ?: throw IllegalStateException("TANI4 dizi yok: ${config.optString("pageApiItems")} url=${response.request.url}")
        val urlField = config.optString("pageApiFieldUrl", "")
        val out = ArrayList<Page>(arr.length())
        for (i in 0 until arr.length()) {
            val raw = if (urlField.isBlank()) {
                arr.optString(i)
            } else {
                jsonField(arr.optJSONObject(i), urlField)
            }
            if (raw.isBlank()) continue
            val u = absolute(raw)
            out.add(Page(out.size, response.request.url.toString(), u))
        }
        return out
    }

    // ---- Qwik düz (flat) durum çözümü ------------------------------------
    // komikrealm.org Qwik ile yazılmış: bölüm sayfasında <img> yok, görseller
    // <bölüm-url>/q-data.json yanıtında duruyor. Biçim:
    // {"_entry":"<b36>","_objs":[ ... ]}
    // Kök: resolve(_entry). Nesne değerleri, dizi elemanları ve metinler base-36
    // indekslerle _objs'e işaret eder; metin öneki kontrol karakteri ise atılır.
    private fun qwikResolve(token: String, objs: JSONArray): Any? {
        val idx = token.trim().toIntOrNull(36) ?: return null
        if (idx < 0 || idx >= objs.length()) return null
        return qwikValue(objs.opt(idx), objs)
    }

    private fun qwikValue(node: Any?, objs: JSONArray): Any? = when (node) {
        is JSONObject -> {
            val out = JSONObject()
            val keys = node.keys()
            while (keys.hasNext()) {
                val k = keys.next()
                val v = node.opt(k)
                val resolved: Any? = if (v is String) qwikResolve(v, objs) else qwikValue(v, objs)
                out.put(k, resolved ?: JSONObject.NULL)
            }
            out
        }
        is JSONArray -> {
            val out = JSONArray()
            for (i in 0 until node.length()) {
                val v = node.opt(i)
                val resolved: Any? = if (v is String) qwikResolve(v, objs) else qwikValue(v, objs)
                out.put(resolved ?: JSONObject.NULL)
            }
            out
        }
        is String -> when {
            node.isEmpty() -> node
            node[0] == '\u0001' -> null
            node[0] >= ' ' -> node
            else -> node.substring(1)
        }
        else -> node
    }

    private fun qwikImageUrl(raw: String): String {
        val u = if (raw.startsWith("http://")) "https://" + raw.removePrefix("http://") else raw
        if (!u.startsWith("https://")) return u
        val host = hostOf(u)
        val direct = config.optString("pageQwikDirectHosts", "")
            .split(',').map { it.trim().lowercase() }.filter { it.isNotEmpty() }
        if (direct.any { host.contains(it) }) return u
        val proxy = config.optString("pageQwikProxy", "")
        if (proxy.isEmpty()) return u
        return proxy + u.removePrefix("https://")
    }

    private fun qwikImages(text: String): List<String> {
        val root = runCatching { JSONObject(text) }.getOrNull() ?: return emptyList()
        val objs = root.optJSONArray("_objs") ?: return emptyList()
        val entry = root.optString("_entry", "")
        val state = qwikResolve(entry, objs) as? JSONObject ?: return emptyList()
        val loaders = state.optJSONObject("loaders") ?: return emptyList()
        var data: JSONObject? = null
        val keys = loaders.keys()
        while (keys.hasNext() && data == null) {
            val loader = loaders.optJSONObject(keys.next()) ?: continue
            if (loader.has("data")) data = loader.optJSONObject("data")
        }
        val chapters = data?.optJSONArray("chapters") ?: return emptyList()
        val images = chapters.optJSONObject(0)?.optJSONObject("images") ?: return emptyList()
        val order = images.keys().asSequence().toList()
            .sortedBy { it.toIntOrNull() ?: Int.MAX_VALUE }
        val out = ArrayList<String>(images.length())
        for (key in order) {
            val src = when (val v = images.opt(key)) {
                is JSONObject -> v.optString("src").trim()
                is String -> v.trim()
                else -> ""
            }
            if (src.isEmpty()) continue
            out.add(qwikImageUrl(src))
        }
        return out
    }

    private fun qwikPages(response: Response): List<Page> {
        val text = response.body?.string().orEmpty()
        val imageUrls = qwikImages(text)
        if (imageUrls.isEmpty()) {
            throw IllegalStateException("TANI-QWIK len=${text.length} ilk=${text.take(160)}")
        }
        // Referer bölüm sayfası olmalı: q-data.json değil.
        val chapterUrl = response.request.url.toString().removeSuffix("/q-data.json")
        return imageUrls.mapIndexed { index, imgUrl -> Page(index, chapterUrl, imgUrl) }
    }

    override fun pageListRequest(chapter: SChapter): Request {
        // Qwik siteleri bölüm verisini yan yanıtta veriyor: <sayfa>/q-data.json
        if (config.optBoolean("pageQwik", false)) {
            val pageUrl = absolute(chapter.url)
            val target = pageUrl.trimEnd('/') + "/q-data.json"
            return Request.Builder()
                .url(target)
                .headers(headers.newBuilder().set("Referer", pageUrl).build())
                .build()
        }
        val api = apiPageUrl(chapter)
        if (api != null) {
            // Bazı sayfa API'leri GET yerine POST bekliyor; gövde form olarak gönderilir.
            if (config.optString("pageApiMethod", "GET").trim().equals("POST", ignoreCase = true)) {
                val body = fillApiBody(chapter, config.optString("pageApiBody", ""))
                return Request.Builder()
                    .url(api)
                    .headers(headers)
                    .post(body.toRequestBody("application/x-www-form-urlencoded".toMediaType()))
                    .build()
            }
            return Request.Builder().url(absolute(api)).headers(headers).build()
        }
        return Request.Builder().url(absolute(chapter.url)).headers(headers).build()
    }

    // Bazı CDN'ler Referer'sız isteği 403 ile reddediyor (amangaplanet.link).
    // Görseli bölüm sayfasını Referer vererek istiyoruz.
    override fun imageRequest(page: Page): Request =
        Request.Builder()
            // Gorsel adresi goreli gelebilir (pageUrlTemplate/script yolu); OkHttp sema ister, absolute() baseUrl ile birlestirir.
            .url(absolute(page.imageUrl.orEmpty()))
            .headers(headers)
            .header("Referer", if (page.url.startsWith("http")) page.url else "$baseUrl/")
            .build()

    // Details
    override fun mangaDetailsParse(response: Response): SManga {
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        return SManga.create().apply {
            url = relativize(response.request.url.toString())
            title = doc.selectFirst("h1, .entry-title")?.text()?.trim() ?: "Manga"
            description = doc.selectFirst("div.description, div.manga-description, div.summary__content, div.entry-content")?.text()?.trim()
            // Görsel etiketi olmayan sitelerde (ör. nemesisscans) kapak og:image'de durur.
            val coverFromImg = doc.selectFirst("div.thumb img, div.manga-poster img, div.summary_image img, img[data-nimg]")?.let { img ->
                img.attr("data-src").ifBlank { null as String? } ?: img.attr("src").ifBlank { null as String? }
            }
            val coverFromMeta = doc.selectFirst("meta[property=og:image]")?.attr("content")?.ifBlank { null }
            thumbnail_url = realImageUrl(coverFromImg ?: coverFromMeta)
            status = SManga.UNKNOWN
        }
    }

    // Chapters
    override fun chapterListParse(response: Response): List<SChapter> {
        // Bazi Madara temalarinda bolum listesi statik HTML'de yok; detay URL'inin
        // yanindaki ajax ucundan HTML parcasi olarak geliyor (or. arthurscan:
        // POST {url}ajax/chapters/). chapterAjaxUrl "{url}" yer tutucusunu tasir.
        val chapterAjax = config.optString("chapterAjaxUrl", "")
        if (chapterAjax.isNotBlank()) {
            val target = absolute(chapterAjax.replace("{url}", response.request.url.toString()))
            val isPost = config.optString("chapterAjaxMethod", "POST").equals("POST", ignoreCase = true)
            val body = config.optString("chapterAjaxBody", "")
            val req = Request.Builder().url(target).headers(headers)
            val ajaxRes = client.newCall(
                if (isPost) req.post(body.toRequestBody("application/x-www-form-urlencoded; charset=UTF-8".toMediaType())).build()
                else if (body.isNotBlank()) req.post(body.toRequestBody("application/x-www-form-urlencoded; charset=UTF-8".toMediaType())).build()
                else req.build()
            ).execute()
            ajaxRes.use { r ->
                val ajaxHtml = r.body?.string().orEmpty()
                val frag = Jsoup.parse(ajaxHtml, baseUrl)
                val ajaxChapters = EngineRegistry.parseChapters(
                    frag,
                    config.optString("chapterSelector", ""),
                    baseUrl,
                )
                if (ajaxChapters.isNotEmpty()) {
                    return ajaxChapters.map { ch ->
                        SChapter.create().apply {
                            url = relativize(ch.url)
                            name = ch.name
                            chapter_number = ch.chapterNumber
                            date_upload = ch.dateUpload
                        }
                    }
                }
            }
        }
        // JSON API yolu gövdeyi apiChapters içinde tüketir; gövdeyi burada
        // okumadan önce ayrılmalı (OkHttp gövdesi tek okumalıktır).
        if (config.optString("chapterApiUrl", "").isNotBlank()) {
            val apiList = apiChapters(response)
            if (apiList.isNotEmpty()) return apiList
            return singleChapterOrEmpty(response)
        }
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val chapterSelector = config.optString("chapterSelector", "")
        val htmlChapters = EngineRegistry.parseChapters(doc, chapterSelector, baseUrl)
        val rscChapters = if (htmlChapters.isEmpty()) {
            EngineRegistry.rscChapters(
                html,
                config.optString("rscChapterUrl", ""),
                response.request.url.toString(),
            )
        } else {
            emptyList<ParsedChapter>()
        }
        val jsonChapters = EngineRegistry.scriptJsonChapters(
            html,
            config.optString("chapterScriptSelector", ""),
            config.optString("chapterScriptContains", ""),
            config.optString("chapterJsonArray", ""),
            config.optString("chapterUrlTemplate", ""),
            response.request.url.toString().trimEnd('/').substringAfterLast('/'),
            baseUrl,
            config.optString("chapterJsonSlugField", "slug"),
            config.optString("chapterJsonNumberField", "number"),
        )
        // Gömülü JSON'dan bölüm listesi varsa DOM sezgisinden üstündür: seçici boş
        // bırakıldığında parseChapters tek bir bağlantı bulup listeyi eksik bırakıyor
        // (nyxscans: 60 bölümün 1'i).
        val chapters = if (jsonChapters.isNotEmpty()) jsonChapters else htmlChapters.ifEmpty { rscChapters }
        val diag = EngineRegistry.diagnose(
            doc, chapterSelector, baseUrl, html,
            response.code, response.request.url.toString(),
        )
        // TANI2: "diag" işaretli kaynaklarda her durumda atılır; cihaz raporu böylece
        // ayrıştırıcının kaç bölüm bulduğunu gösterir. Geçici ölçüm kipi.
        if (config.optString("diag", "").isNotBlank()) {
            throw IllegalStateException(
                "TANI2 gen=${chapters.size} html=${htmlChapters.size} rsc=${rscChapters.size} $diag",
            )
        }
        // Bölümü olmayan seri (ör. yeni eklenmiş, "0 bölüm") kaynağı kırmamalı:
        // Mihon sözleşmesi boş liste döndürmektir. TANI2 kipi ölçüm için atmayı sürdürür.
        if (chapters.isEmpty()) {
            return singleChapterOrEmpty(response)
        }

        return chapters.map { ch ->
            SChapter.create().apply {
                url = relativize(ch.url)
                name = ch.name
                chapter_number = ch.chapterNumber
                date_upload = ch.dateUpload
            }
        }
    }

    // Tek bölümlü kaynak (singleChapter): galeri/booru tipi sitelerde (8muses,
    // e621, elitebabes, girlstop, doujins.com, de.fsicomics, de.wporncomics)
    // detay sayfası hem seri hem bölüm sayfasıdır; bölüm bağlantısı yoktur ve
    // chapterListParse boş liste dönüyordu ("0 bölüm"). singleChapter açıksa
    // serinin kendi adresi tek bölüm olarak döner; pageListParse değişmez,
    // detay sayfasını readerSelector / pageScript* / pageApi* yoluyla ayrıştırır.
    // Ayar kapalıyken (varsayılan) davranış eskisiyle birebir aynıdır: boş liste.
    private fun singleChapterOrEmpty(response: Response): List<SChapter> {
        if (!config.optBoolean("singleChapter", false)) return emptyList()
        val label = config.optString("singleChapterName", "Bölüm").trim().ifBlank { "Bölüm" }
        return listOf(
            SChapter.create().apply {
                url = relativize(response.request.url.toString())
                this.name = label
                chapter_number = 1f
            },
        )
    }

    // Sayfa sayısını JS ile hesaplayan galeriler (hentaiforce /view/<id>/<n>,
    // hentaifox /g/<id>/<n>/): "sonraki" bağlantısı href taşımaz, sayfa zinciri
    // bu yüzden kurulamaz. pageSeqUrl şablonunda {url} bölüm adresi, {n} sayfa
    // numarasıdır; adet pageSeqCount ya da pageSeqCountSelector'ün metninden gelir.
    private fun seqPages(doc: Document, chapterUrl: String): List<Page> {
        val template = config.optString("pageSeqUrl", "").trim()
        if (template.isEmpty()) return emptyList()
        val count = config.optInt("pageSeqCount", 0).takeIf { it > 0 }
            ?: seqCountFrom(doc)
            ?: return emptyList()
        val start = config.optInt("pageSeqStart", 1).let { if (it > 0) it else 1 }
        val total = count.coerceAtMost(400)
        return (0 until total).map { i ->
            val n = start + i
            val u = template.replace("{url}", chapterUrl).replace("{n}", n.toString())
            Page(i, chapterUrl, absolute(u))
        }
    }

    private fun seqCountFrom(doc: Document): Int? {
        val sel = config.optString("pageSeqCountSelector", "").trim()
        if (sel.isEmpty()) return null
        val el = doc.selectFirst(sel) ?: return null
        val attr = config.optString("pageSeqCountAttr", "").trim()
        val raw = if (attr.isEmpty() || attr.equals("text", ignoreCase = true)) el.text() else el.attr(attr)
        return Regex("\\d+").find(raw)?.value?.toIntOrNull()?.takeIf { it > 0 }
    }

    // Pages
    override fun pageListParse(response: Response): List<Page> {
        if (config.optBoolean("pageQwik", false)) {
            return qwikPages(response)
        }
        // API yanıtı HTML değil JSON belgesidir; gövdeyi tüketmeden ilk bayta bakılır.
        // Kök dizi ([) de sayfa API'si olabilir; JSONObject yolu değişmeden durur.
        if (config.optString("pageApiUrl", "").isNotBlank() &&
            response.peekBody(1).string().trimStart().let { it.startsWith("{") || it.startsWith("[") }
        ) {
            return apiPages(response)
        }
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val chapterUrl = response.request.url.toString()
        // pageSeqFirst doluysa sayısal dizi diğer yollardan önce denenir.
        if (config.optString("pageSeqFirst", "").isNotBlank()) {
            val seq = seqPages(doc, chapterUrl)
            if (seq.isNotEmpty()) return seq
        }
        val imageUrls = pageImagesFrom(doc, html).toMutableList()

        // Çok sayfalı okuyucu zinciri: bazı sitelerde bölüm tek HTML değil, ayrı
        // belgelerden oluşur (niadd: /chapter/x/123/ -> /chapter/x/123-2.html ...).
        // pageNextSelector boşsa davranış eskisiyle birebir aynıdır.
        val nextSelector = config.optString("pageNextSelector", "").trim()
        if (nextSelector.isNotBlank()) {
            val limit = config.optInt("pageNextLimit", 30).let { if (it > 0) it else 30 }
            // pageNextPattern: bağlantının "sonraki sayfa" olduğunu doğrulayan isteğe
            // bağlı regex (ör. niadd "-2.html" son eki). Boşsa seçici tek başına yeter.
            val pattern = config.optString("pageNextPattern", "").trim()
                .takeIf { it.isNotBlank() }
                ?.let { runCatching { Regex(it) }.getOrNull() }
            val visited = HashSet<String>()
            visited.add(normalizeUrl(chapterUrl))
            val chapterDir = pageDir(chapterUrl)
            var currentDoc = doc
            var currentUrl = chapterUrl
            var followed = 0
            while (followed < limit) {
                val next = nextPageUrl(currentDoc, nextSelector, currentUrl, pattern) ?: break
                // Döngü koruması: aynı adresi ikinci kez çekme.
                if (!visited.add(normalizeUrl(next))) break
                // Bölüm sınırı: son sayfanın "Next" bağlantısı sonraki bölüme
                // gider; aynı dizinde kalmayan bağlantı izlenmez.
                if (pageDir(next) != chapterDir) break
                // 2. sayfa ve sonrası hata verirse elde edilen görsellerle dön.
                val fetched = runCatching { fetchPageDocument(next, currentUrl) }.getOrNull() ?: break
                val imgs = pageImagesFrom(fetched.first, fetched.second)
                if (imgs.isEmpty()) break
                imageUrls.addAll(imgs)
                currentDoc = fetched.first
                currentUrl = fetched.third
                followed++
            }
        }

        // readerSelector/script/chain yolları sayfa bulamadıysa sayısal dizi devreye girer.
        if (imageUrls.isEmpty()) {
            val seq = seqPages(doc, chapterUrl)
            if (seq.isNotEmpty()) return seq
        }

        return imageUrls.mapIndexed { index, imgUrl ->
            Page(index, chapterUrl, imgUrl)
        }
    }

    // Tek bir bölüm belgesinden görsel adreslerini çıkarır. İlk sayfa ve zincirin
    // sonraki sayfaları aynı yolu kullanır (davranış tek yerde kalır).
    private fun pageImagesFrom(doc: Document, html: String): List<String> {
        val scriptPages = EngineRegistry.scriptJsonPages(
            html,
            config.optString("pageScriptSelector", ""),
            config.optString("pageJsonUrlField", ""),
            config.optString("pageJsonArray", ""),
            baseUrl,
            config.optString("pageUrlAllow", ""),
            config.optString("pageScriptContains", ""),
            config.optString("pageUrlBase", ""),
        )
        // Next.js App Router siteleri sayfa dizisini RSC "flight" metnine gömüyor
        // (hentailek, pornhwareader). pageRscKey boşsa (varsayılan) hiç çalışmaz.
        val rscPages = EngineRegistry.rscPageImages(
            html,
            config.optString("pageRscKey", ""),
            config.optString("pageRscUrlField", ""),
            config.optString("pageUrlBase", "").ifBlank { baseUrl },
            config.optString("pageUrlAllow", ""),
        )
        // Bazı sitelerde DOM içindeki <img> adresleri doğrudan çalışmıyor (Amanga: .link
        // originde 403). Site kendi okuyucusunda <script> içindedir ve proxy adresi
        // üretir; "pageScriptFirst" işaretliyse script sonucu DOM içeriğinden önce gelir.
        val scriptFirst = config.optString("pageScriptFirst", "").isNotBlank() && scriptPages.isNotEmpty()
        return if (scriptFirst) {
            scriptPages
        } else {
            EngineRegistry.parsePages(
                doc,
                config.optString("readerSelector", ""),
                baseUrl,
                config.optString("pageUrlTemplate", ""),
            )
                .ifEmpty { EngineRegistry.rawImages(html, baseUrl) }
                .ifEmpty { scriptPages }
                .ifEmpty { rscPages }
        }
    }

    // Sayfa zincirindeki "sonraki" bağlantısını çözer. Göreli href geçerli sayfa
    // adresine göre mutlaklaştırılır (-2.html gibi kısa yollar baseUrl köküne değil).
    private fun nextPageUrl(doc: Document, selector: String, currentUrl: String, pattern: Regex?): String? {
        val el = doc.selectFirst(selector) ?: return null
        val href = el.attr("href").trim()
        if (href.isBlank() || href == "#" || href.startsWith("javascript:", ignoreCase = true)) return null
        if (pattern != null && !pattern.containsMatchIn(href)) return null
        return resolveAgainst(currentUrl, href)
    }

    private fun resolveAgainst(base: String, ref: String): String {
        val t = ref.trim()
        if (t.startsWith("http://") || t.startsWith("https://")) return t
        return runCatching { java.net.URI(base).resolve(t).toString() }.getOrElse { absolute(t) }
    }

    private fun normalizeUrl(url: String): String =
        runCatching { java.net.URI(url.trim()).normalize().toString() }
            .getOrDefault(url.trim())
            .substringBefore("#")

    // Zincirdeki sayfaların ortak dizini. Sondaki / atılır: niadd bölüm başlangıcı
    // "/chapter/x/123/" iken sonraki sayfalar "/chapter/x/123-2.html" biçiminde.
    private fun pageDir(url: String): String =
        url.substringBefore("#").substringBefore("?").trimEnd('/').substringBeforeLast('/', "")

    private fun fetchPageDocument(url: String, referer: String): Triple<Document, String, String> {
        val req = Request.Builder()
            .url(url)
            .headers(headers.newBuilder().set("Referer", referer).build())
            .build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("HTTP ${resp.code}")
            val body = resp.body?.string().orEmpty()
            if (body.isBlank()) throw IllegalStateException("boş gövde")
            return Triple(Jsoup.parse(body, url), body, resp.request.url.toString())
        }
    }

    override fun imageUrlParse(response: Response): String = throw UnsupportedOperationException()
}
