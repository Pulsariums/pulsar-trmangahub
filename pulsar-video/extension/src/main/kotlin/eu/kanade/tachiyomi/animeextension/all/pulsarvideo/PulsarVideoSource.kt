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
import okhttp3.Request
import okhttp3.Response
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
                title = el.selectFirst(config.optString("titleSelector", ""))?.text()
                    ?: a.text().ifBlank { "?" }
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
        return doc.select(sel).mapNotNull { el ->
            val a = if (el.tagName() == "a") el else el.selectFirst("a[href]") ?: return@mapNotNull null
            val url = a.absUrl("href").ifBlank { a.attr("href") }
            if (url.isBlank()) return@mapNotNull null
            Hoster(url, a.text().ifBlank { "embed" })
        }
    }

    override fun videoListRequest(hoster: Hoster): Request = req(hoster.hosterUrl)

    override fun videoListParse(response: Response, hoster: Hoster): List<Video> {
        val body = response.body?.string().orEmpty()

        // 1) Doğrudan akış (m3u8/mp4)
        val direct = Regex("(https?:[^\"'\s]+\.(?:m3u8|mp4)[^\"'\s]*)").find(body)?.groupValues?.get(1)
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

    private fun req(url: String): Request = Request.Builder()
        .url(if (url.startsWith("http")) url else "$baseUrl/${url.trimStart('/')}")
        .headers(headers)
        .build()

    private fun Response.asJsoup(): Document = Jsoup.parse(body?.string().orEmpty(), baseUrl)
}
