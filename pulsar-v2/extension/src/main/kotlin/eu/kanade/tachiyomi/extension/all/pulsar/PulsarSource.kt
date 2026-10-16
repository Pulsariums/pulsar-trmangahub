package eu.kanade.tachiyomi.extension.all.pulsar

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.online.HttpSource
import okhttp3.Headers
import okhttp3.OkHttpClient
import okhttp3.Request
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

    override val supportsLatest: Boolean = true

    override val client: OkHttpClient by lazy {
        network.client.newBuilder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .followRedirects(true)
            .build()
    }

    override fun headersBuilder(): Headers.Builder = super.headersBuilder()
        .add("Referer", "$baseUrl/")
        .add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

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
                url = item.url
                title = item.title
                thumbnail_url = item.coverUrl
            }
        }
        return MangasPage(mangas, hasNextPage = mangas.size >= 10)
    }

    // Latest Updates
    override fun latestUpdatesRequest(page: Int): Request = popularMangaRequest(page)
    override fun latestUpdatesParse(response: Response): MangasPage = popularMangaParse(response)

    // Search
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val searchUrl = "$baseUrl/?s=$query"
        return Request.Builder().url(searchUrl).headers(headers).build()
    }

    override fun searchMangaParse(response: Response): MangasPage = popularMangaParse(response)

    // Details
    override fun mangaDetailsParse(response: Response): SManga {
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        return SManga.create().apply {
            title = doc.selectFirst("h1, .entry-title")?.text()?.trim() ?: "Manga"
            description = doc.selectFirst("div.description, div.manga-description, div.summary__content, div.entry-content")?.text()?.trim()
            thumbnail_url = doc.selectFirst("div.thumb img, div.manga-poster img, div.summary_image img")?.let { img ->
                img.attr("data-src").ifBlank { null as String? } ?: img.attr("src").ifBlank { null as String? }
            }
            status = SManga.UNKNOWN
        }
    }

    // Chapters
    override fun chapterListParse(response: Response): List<SChapter> {
        val html = response.body?.string().orEmpty()
        val doc = Jsoup.parse(html, baseUrl)
        val chapterSelector = config.optString("chapterSelector", "")
        val chapters = EngineRegistry.parseChapters(doc, chapterSelector, baseUrl)

        return chapters.map { ch ->
            SChapter.create().apply {
                url = ch.url
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

        return imageUrls.mapIndexed { index, imgUrl ->
            Page(index, "", imgUrl)
        }
    }

    override fun imageUrlParse(response: Response): String = throw UnsupportedOperationException()
}
