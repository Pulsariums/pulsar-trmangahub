package eu.kanade.tachiyomi.extension.all.pulsar.native

import android.util.Base64
import eu.kanade.tachiyomi.extension.all.pulsar.PulsarSource
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import okhttp3.Request
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import java.net.URLEncoder

/**
 * 嬉皮漫畫 (HipManga / Copy20 hasadı, 2026-11-24).
 *
 * Config motoru bu siteyi ifade edemiyordu:
 *  - liste HTML (`/popularity`), son güncellemeler ve arama JSON API'de,
 *  - bölüm listesi detay sayfasındaki `data-mid` ile API'den geliyor,
 *  - okuyucu sayfa adresleri `/v2/chapter?hid=` yanıtındaki **kodlanmış**
 *    `images` alanından çözülüyor (sabit önek/sonek, 7'lik parça ters çevirme,
 *    özel alfabeli Base64). Şifre değil; bytecode'daki sabitlerle deterministik.
 */
class HipmhSource(
    rawConfig: JSONObject,
    lang: String,
) : PulsarSource(rawConfig, lang) {

    private val apiBase = "https://hipapi1.s3file.top"
    private val readerBase = "https://reader.hipmh.top"
    private val coverBase = "https://cover.s3imgs.top"

    // ---- Liste -------------------------------------------------------------

    override fun popularMangaRequest(page: Int): Request {
        val url = if (page > 1) "$baseUrl/popularity?page=$page" else "$baseUrl/popularity"
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun popularMangaParse(response: Response): MangasPage {
        val document = doc(response)
        val cards = document.select("a.manga-card-link[href^=/works/]")
        val mangas = cards.mapNotNull { a ->
            val href = a.attr("href").trim()
            if (!href.startsWith("/works/")) return@mapNotNull null
            SManga.create().apply {
                url = href
                title = a.attr("aria-label").trim()
                    .ifBlank { a.selectFirst(".manga-card-title, h3, h2")?.text()?.trim().orEmpty() }
                    .ifBlank { a.selectFirst("img[alt]")?.attr("alt")?.trim().orEmpty() }
                    .ifBlank { "?" }
                thumbnail_url = coverOf(a.selectFirst("img")?.attr("src"))
            }
        }
        val hasNext = document.selectFirst("a.pagination-next[href]:not([aria-disabled=true])") != null
        return MangasPage(mangas, hasNextPage = hasNext)
    }

    override fun latestUpdatesRequest(page: Int): Request =
        Request.Builder().url("$apiBase/v1/mangas?sort=updated&page=$page&per_page=18")
            .headers(headers).build()

    override fun latestUpdatesParse(response: Response): MangasPage = parseApiList(response, "items")

    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val url = "$apiBase/v1/search?q=" + URLEncoder.encode(query, "UTF-8") +
            "&page=$page&page_size=20"
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun searchMangaParse(response: Response): MangasPage = parseApiList(response, "data")

    private fun parseApiList(response: Response, itemsKey: String): MangasPage {
        val text = response.body?.string().orEmpty()
        val data = runCatching { JSONObject(text).optJSONObject("data") }.getOrNull()
            ?: return MangasPage(emptyList(), false)
        val items = data.optJSONArray(itemsKey) ?: return MangasPage(emptyList(), false)
        val mangas = (0 until items.length()).mapNotNull { i ->
            val o = items.optJSONObject(i) ?: return@mapNotNull null
            val id = o.optString("mid", "").ifBlank { o.optString("id", "") }.trim()
            if (id.isEmpty()) return@mapNotNull null
            SManga.create().apply {
                url = "/works/$id"
                title = o.optString("title", "").trim().ifBlank { "?" }
                val img = o.optString("vertical_image_url", "").ifBlank {
                    o.optString("cover_image_url", "")
                }
                thumbnail_url = coverOf(img)
            }
        }
        val page = data.optInt("page", 1)
        val totalPages = data.optInt("total_pages", 1)
        return MangasPage(mangas, hasNextPage = page < totalPages)
    }

    // ---- Detay / bölümler --------------------------------------------------

    override fun mangaDetailsParse(response: Response): SManga {
        val document = doc(response)
        return SManga.create().apply {
            url = response.request.url.encodedPath
            title = document.selectFirst("h1")?.text()?.trim()
                ?.ifBlank { null } ?: document.title().trim().ifBlank { "?" }
            author = document.select("a[href^=/author/]").joinToString(", ") { it.text().trim() }
                .ifBlank { null }
            genre = document.select("a[href^=/tag/], a[href^=/genre/]")
                .joinToString(", ") { it.text().trim() }.ifBlank { null }
            description = document.selectFirst("#d-info-content p")?.text()?.trim()
                ?: document.selectFirst("#d-info-content")?.text()?.trim()
            val cover = document.selectFirst("#d-info-content img, main img")
                ?.let { it.attr("src").ifBlank { it.attr("data-cover") } }
            thumbnail_url = coverOf(cover)
        }
    }

    override fun chapterListParse(response: Response): List<SChapter> {
        val document = doc(response)
        val mid = document.selectFirst("#chapters-config")?.attr("data-mid")?.trim().orEmpty()
        if (mid.isEmpty() || !MID_PATTERN.matches(mid)) return emptyList()
        val text = runCatching {
            Request.Builder().url("$apiBase/v1/manga/chapters?mid=$mid&per_page=200&order=desc")
                .headers(headers).build()
                .let { req -> client.newCall(req).execute().use { if (it.isSuccessful) it.body?.string().orEmpty() else "" } }
        }.getOrDefault("")
        val items = runCatching {
            JSONObject(text).optJSONObject("data")?.optJSONArray("items")
        }.getOrNull() ?: return emptyList()
        return (0 until items.length()).mapNotNull { i ->
            val o = items.optJSONObject(i) ?: return@mapNotNull null
            val hid = o.optString("hid", "").trim()
            if (hid.isEmpty()) return@mapNotNull null
            SChapter.create().apply {
                url = "/chapter/$hid"
                name = o.optString("title", "").trim().ifBlank { "Bölüm" }
                chapter_number = o.optString("chapter_number", "0").toFloatOrNull() ?: -1f
                date_upload = parseDate(o.optString("updated_at", ""))
            }
        }
    }

    // ---- Okuyucu -----------------------------------------------------------

    override fun pageListRequest(chapter: SChapter): Request =
        Request.Builder().url(readerBase + chapter.url).headers(headers).build()

    override fun pageListParse(response: Response): List<Page> {
        val document = doc(response)
        val config = document.selectFirst("#chapcontent") ?: return emptyList()
        val apiHid = config.attr("data-api-hid").trim()
        if (apiHid.isEmpty()) return emptyList()
        val api = config.attr("data-api-base-url-line1").trim().ifBlank {
            config.attr("data-api-base-url").trim().ifBlank { apiBase }
        }.trimEnd('/')
        val images = fetchImages(api, apiHid) ?: return emptyList()
        val line = images.second
        val payload = images.first
        if (payload.isEmpty()) return emptyList()
        val special = line == 9
        val imageBase = if (special) {
            config.attr("data-chapter-img-base-line1s").trim()
        } else {
            config.attr("data-chapter-img-base-line1").trim()
        }.ifBlank { "https://hip-tx-1.s3imgs.top" }

        val readerUrl = response.request.url.toString()
        return decodePaths(payload).mapIndexedNotNull { i, path ->
            val url = when {
                path.startsWith("http://") || path.startsWith("https://") -> path
                path.startsWith("/") -> imageBase.trimEnd('/') + path
                else -> imageBase.trimEnd('/') + "/" + path
            }
            if (!url.startsWith("https://")) return@mapIndexedNotNull null
            Page(i, readerUrl, url)
        }.distinctBy { it.imageUrl }
    }

    /** `/v2/chapter?hid=` yanıtı: (images alanı, line). */
    private fun fetchImages(api: String, hid: String): Pair<String, Int>? {
        val text = runCatching {
            Request.Builder().url("$api/v2/chapter?hid=$hid").headers(headers).build()
                .let { req -> client.newCall(req).execute().use { if (it.isSuccessful) it.body?.string().orEmpty() else "" } }
        }.getOrNull().orEmpty()
        val root = runCatching { JSONObject(text) }.getOrNull() ?: return null
        if (root.optInt("code", 0) != 200) return null
        val data = root.optJSONObject("data") ?: return null
        val images = data.opt("images")
        val line = data.optInt("line", 0)
        return when (images) {
            is JSONArray -> images.toString() to line
            is String -> images to line
            else -> null
        }
    }

    /** `images` alanı JSON dizisi ya da kodlanmış metin olabilir. */
    private fun decodePaths(raw: String): List<String> {
        val text = raw.trim()
        if (text.startsWith("[")) {
            return runCatching {
                val arr = JSONArray(text)
                (0 until arr.length()).map { arr.getString(it) }
            }.getOrDefault(emptyList())
        }
        if (text.length <= 10 || !text.startsWith("qM9") || !text.endsWith("Z7")) return emptyList()
        val t = text.substring(3, text.length - 2)
        val y = t.indexOf("Vx")
        val x = t.indexOf("pL0")
        if (y < 0 || x < 0 || x <= y) return emptyList()
        val rebuilt = t.substring(x + 3) + t.substring(0, y) + t.substring(y + 2, x)
        val sb = StringBuilder(rebuilt.length)
        var i = 0
        var chunkIndex = 0
        while (i < rebuilt.length) {
            val end = minOf(i + 7, rebuilt.length)
            val chunk = rebuilt.substring(i, end)
            sb.append(if (chunkIndex % 2 == 1) chunk.reversed() else chunk)
            i = end
            chunkIndex++
        }
        val mapped = buildString(sb.length) {
            for (ch in sb) {
                val idx = CUSTOM_ALPHABET.indexOf(ch)
                append(if (idx >= 0) STD_ALPHABET[idx] else ch)
            }
        }
        val bytes = runCatching {
            Base64.decode(mapped, Base64.URL_SAFE or Base64.NO_WRAP)
        }.getOrNull() ?: return emptyList()
        val json = String(bytes, Charsets.UTF_8)
        return runCatching {
            val arr = JSONArray(json)
            (0 until arr.length()).map { arr.getString(it) }
        }.getOrDefault(emptyList())
    }

    override fun imageUrlParse(response: Response): String = response.request.url.toString()

    // ---- Yardımcılar -------------------------------------------------------

    private fun coverOf(raw: String?): String? {
        val v = raw?.trim().orEmpty()
        if (v.isEmpty()) return null
        return when {
            v.startsWith("http://") || v.startsWith("https://") -> v
            v.startsWith("//") -> "https:$v"
            v.startsWith("/") -> coverBase + v
            else -> "$coverBase/$v"
        }
    }

    private fun parseDate(raw: String): Long = runCatching {
        java.time.OffsetDateTime.parse(raw).toInstant().toEpochMilli()
    }.getOrDefault(0L)

    private fun doc(response: Response): Document =
        Jsoup.parse(response.body?.string().orEmpty(), baseUrl)

    private companion object {
        val MID_PATTERN = Regex("[A-Za-z0-9_-]+")
        const val CUSTOM_ALPHABET = "_-9876543210abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        const val STD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    }
}
