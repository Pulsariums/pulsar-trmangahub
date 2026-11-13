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
            val u = o.optString(urlKey).trim()
            if (u.isEmpty()) return@mapNotNull null
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

    override fun chapterListRequest(manga: SManga): Request =
        Request.Builder().url(absolute(manga.url)).headers(headers).build()

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
        val imageUrls = EngineRegistry.parsePages(doc, readerSelector, baseUrl)

        val chapterUrl = response.request.url.toString()
        return imageUrls.mapIndexed { index, imgUrl ->
            Page(index, chapterUrl, imgUrl)
        }
    }

    override fun imageUrlParse(response: Response): String = throw UnsupportedOperationException()
}
