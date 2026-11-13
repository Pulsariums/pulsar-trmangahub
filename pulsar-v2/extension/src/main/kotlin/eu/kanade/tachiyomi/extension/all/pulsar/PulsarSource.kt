package eu.kanade.tachiyomi.extension.all.pulsar

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.HttpSource
import okhttp3.Headers
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import org.jsoup.Jsoup
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
    private val desktopUserAgent: String =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

    override val supportsLatest: Boolean = true

    override val client: OkHttpClient by lazy {
        network.client.newBuilder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .followRedirects(true)
            // Amanga Planet'in görsel CDN'i isteğe göre aralıklı 403 veriyor
            // (aynı URL 10 GET'in 4'ünde 200 dönüyor, çerez/UA/Referer etkisiz).
            // Yalnız GET + 403 için kısa aralıklarla yeniden deniyoruz.
            .addInterceptor { chain ->
                val request = chain.request()
                var response = chain.proceed(request)
                var attempt = 0
                while (response.code == 403 && attempt < 3 && request.method == "GET") {
                    response.close()
                    attempt++
                    Thread.sleep(250L * attempt)
                    response = chain.proceed(request)
                }
                response
            }
            .build()
    }

    override fun headersBuilder(): Headers.Builder = super.headersBuilder()
        .removeAll("User-Agent")
        .add("Referer", "$baseUrl/")
        .add("User-Agent", desktopUserAgent)

    override val id: Long by lazy {
        val key = "pulsar/$domain/$lang"
        var h = 1125899906842597L
        for (ch in key) h = 31 * h + ch.code
        h and Long.MAX_VALUE
    }

    // Popular Manga
    override fun popularMangaRequest(page: Int): Request {
        val listPath = config.optString("listPath", "/manga").trimStart('/')
        val url = if (page > 1) "$baseUrl/$listPath?page=$page" else "$baseUrl/$listPath"
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun popularMangaParse(response: Response): MangasPage {
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val itemSelector = config.optString("itemSelector", "")
        val items = EngineRegistry.parseList(doc, itemSelector, baseUrl)
            .ifEmpty { EngineRegistry.rscList(html, baseUrl) }

        val mangas = items.map { item ->
            SManga.create().apply {
                url = relativize(item.url)
                title = item.title
                thumbnail_url = realImageUrl(item.coverUrl)
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
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val apiUrl = config.optString("searchUrl", "")
        if (apiUrl.isBlank()) {
            return Request.Builder().url("$baseUrl/?s=$query").headers(headers).build()
        }
        val isPost = config.optString("searchMethod", "GET").equals("POST", ignoreCase = true)
        if (!isPost) {
            val target = apiUrl.replace("{query}", query)
            return Request.Builder().url(target).headers(headers).build()
        }
        val target = if (page > 1) "$apiUrl&page=$page" else apiUrl
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
        val arr = runCatching { JSONObject(text).optJSONArray(arrayKey) }.getOrNull()
            ?: return MangasPage(emptyList(), hasNextPage = false)
        val urlKey = config.optString("searchJsonUrl", "url")
        val titleKey = config.optString("searchJsonTitle", "title")
        val mangas = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            val raw = o.optString(urlKey).trim()
            if (raw.isEmpty()) return@mapNotNull null
            val prefix = config.optString("searchJsonPathPrefix", "")
            val u = if (prefix.isNotEmpty() && !raw.startsWith("http") && !raw.startsWith("/")) {
                prefix.trimEnd('/') + "/" + raw.trimStart('/')
            } else {
                raw
            }
            SManga.create().apply {
                url = relativize(u)
                title = o.optString(titleKey).trim()
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
        val abs = if (u.startsWith("http")) u else "$baseUrl/${u.trimStart('/')}"
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

    // ---- URL birleştirme -------------------------------------------------
    // EngineRegistry MUTLAK URL üretir (https://site/manga/x). HttpSource ise
    // istek kurarken baseUrl + manga.url yapar; ikisi birleşince host
    // "site.comhttps" oluyordu. Cihaz raporu: Unable to resolve host
    // "anikiga.comhttps" — Amanga Planet, Anikiga, Rüya Manga bu yüzden düştü.
    private fun absolute(url: String): String =
        if (url.startsWith("http://") || url.startsWith("https://")) url
        else "$baseUrl/${url.trimStart('/')}"

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
        val arr = runCatching { org.json.JSONObject(text).optJSONArray(itemsKey) }.getOrNull()
            ?: throw IllegalStateException(
                "TANI3 api url=${response.request.url} len=${text.length} ilk=${text.take(160)}",
            )
        val nameKey = config.optString("chapterApiFieldName", "name")
        val numKey = config.optString("chapterApiFieldNumber", "number")
        val urlKey = config.optString("chapterApiFieldUrl", "url")
        val out = ArrayList<SChapter>(arr.length())
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val raw = o.optString(urlKey).trim()
            if (raw.isEmpty()) continue
            val num = o.optString(numKey).replace(',', '.').toFloatOrNull() ?: 0f
            val title = o.optString(nameKey).trim().ifBlank { "Bölüm " + num }
            out.add(
                SChapter.create().apply {
                    url = relativize(raw)
                    name = title
                    chapter_number = num
                    date_upload = 0L
                },
            )
        }
        return out
    }

    override fun chapterListRequest(manga: SManga): Request {
        val api = apiChapterUrl(manga)
        if (api != null) return Request.Builder().url(api).headers(headers).build()
        return Request.Builder().url(absolute(manga.url)).headers(headers).build()
    }

    override fun pageListRequest(chapter: SChapter): Request =
        Request.Builder().url(absolute(chapter.url)).headers(headers).build()

    // Bazı CDN'ler Referer'sız isteği 403 ile reddediyor (amangaplanet.link).
    // Görseli bölüm sayfasını Referer vererek istiyoruz.
    override fun imageRequest(page: Page): Request =
        Request.Builder()
            .url(page.imageUrl.orEmpty())
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
            thumbnail_url = realImageUrl(
                doc.selectFirst("div.thumb img, div.manga-poster img, div.summary_image img, img[data-nimg]")?.let { img ->
                    img.attr("data-src").ifBlank { null as String? } ?: img.attr("src").ifBlank { null as String? }
                },
            )
            status = SManga.UNKNOWN
        }
    }

    // Chapters
    override fun chapterListParse(response: Response): List<SChapter> {
        // JSON API yolu gövdeyi apiChapters içinde tüketir; gövdeyi burada
        // okumadan önce ayrılmalı (OkHttp gövdesi tek okumalıktır).
        if (config.optString("chapterApiUrl", "").isNotBlank()) {
            return apiChapters(response)
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
        val chapters = htmlChapters.ifEmpty { rscChapters }
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
        if (chapters.isEmpty()) {
            throw IllegalStateException(diag)
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

    // Pages
    override fun pageListParse(response: Response): List<Page> {
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val readerSelector = config.optString("readerSelector", "")
        val scriptPages = EngineRegistry.scriptJsonPages(
            html,
            config.optString("pageScriptSelector", ""),
            config.optString("pageJsonUrlField", ""),
            config.optString("pageJsonArray", ""),
            baseUrl,
            config.optString("pageUrlAllow", ""),
        )
        // Bazı sitelerde DOM'daki <img> adresleri doğrudan çalışmıyor (Amanga: .link
        // origin'de 403). Site kendi okuyucusunda <script> içindedir ve proxy adresi
        // üretir; "pageScriptFirst" işaretliyse script sonucu DOM'dan önce gelir.
        val scriptFirst = config.optString("pageScriptFirst", "").isNotBlank() && scriptPages.isNotEmpty()
        val imageUrls = if (scriptFirst) {
            scriptPages
        } else {
            EngineRegistry.parsePages(doc, readerSelector, baseUrl)
                .ifEmpty { EngineRegistry.rawImages(html, baseUrl) }
                .ifEmpty { scriptPages }
        }

        val chapterUrl = response.request.url.toString()
        return imageUrls.mapIndexed { index, imgUrl ->
            Page(index, chapterUrl, imgUrl)
        }
    }

    override fun imageUrlParse(response: Response): String = throw UnsupportedOperationException()
}
