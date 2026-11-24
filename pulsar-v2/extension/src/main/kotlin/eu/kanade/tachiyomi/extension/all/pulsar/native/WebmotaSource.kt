package eu.kanade.tachiyomi.extension.all.pulsar.native

import eu.kanade.tachiyomi.extension.all.pulsar.PulsarSource
import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import okhttp3.Headers
import okhttp3.Request
import okhttp3.Response
import org.json.JSONObject
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import java.net.URI
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Locale

/**
 * 包子漫画 (BaoziManhuaPlus / Copy20 hasadı, 2026-11-24).
 *
 * Config motoru bu siteyi ifade edemiyordu:
 *  - liste JSON'u AMP uçundan (`/api/bzmhq/amp_comic_list`),
 *  - detayda bölümler yalnız `?section_slot=0` ile sunucu tarafında render ediliyor,
 *  - bölüm bağlantısı `/user/page_direct?...` (302 → `/comic/chapter/...`),
 *  - okuyucu sayfaları AMP durum JSON'undan (`amp-state[id^=chapter][id$=Src]`) geliyor.
 *
 * Kimlik doğrulama statik başlık sabitleri (imza/HMAC yok); Cloudflare 403'ünde
 * rastgele `app*.baozimh.com` + `/baozimhapp` yoluna düşülür.
 */
class WebmotaSource(
    rawConfig: JSONObject,
    lang: String,
) : PulsarSource(rawConfig, lang) {

    // ---- Liste -------------------------------------------------------------

    override fun popularMangaRequest(page: Int): Request {
        val url = "$baseUrl/api/bzmhq/amp_comic_list" +
            "?type=all&region=all&state=all&filter=*&page=$page&limit=36&language=tw" +
            "&__amp_source_origin=$baseUrl"
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun popularMangaParse(response: Response): MangasPage {
        val text = response.body?.string().orEmpty()
        val root = runCatching { JSONObject(text) }.getOrNull()
            ?: return MangasPage(emptyList(), false)
        val items = root.optJSONArray("items") ?: return MangasPage(emptyList(), false)
        val mangas = (0 until items.length()).mapNotNull { i ->
            val o = items.optJSONObject(i) ?: return@mapNotNull null
            val id = o.optString("comic_id", "").trim()
            if (id.isEmpty()) return@mapNotNull null
            SManga.create().apply {
                url = "/comic/$id"
                title = o.optString("name", "").trim().ifBlank { "?" }
                author = o.optString("author", "").trim().ifBlank { null }
                genre = o.optJSONArray("type_names")?.let { arr ->
                    (0 until arr.length()).joinToString(", ") { arr.optString(it) }
                }?.takeIf { it.isNotBlank() }
                thumbnail_url = coverOf(o.optString("topic_img", ""))
            }
        }
        return MangasPage(mangas, hasNextPage = root.optString("next", "").isNotBlank())
    }

    override fun latestUpdatesRequest(page: Int): Request =
        Request.Builder().url("$baseUrl/list/new?page=$page").headers(headers).build()

    override fun latestUpdatesParse(response: Response): MangasPage = parseCards(doc(response))

    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request {
        val url = "$baseUrl/search?q=" + URLEncoder.encode(query, "UTF-8")
        return Request.Builder().url(url).headers(headers).build()
    }

    override fun searchMangaParse(response: Response): MangasPage {
        if (response.request.url.toString().contains("/api/bzmhq/amp_comic_list")) {
            return popularMangaParse(response)
        }
        return parseCards(doc(response))
    }

    /** Arama ve "son güncellemeler" aynı kart yapısını kullanır. */
    private fun parseCards(document: Document): MangasPage {
        val cards = document.select("div.comics-card, div.pure-g div a.comics-card__poster")
        val mangas = cards.mapNotNull { el ->
            val link = if (el.tagName() == "a" && el.hasAttr("href")) el else el.selectFirst("a[href]")
                ?: return@mapNotNull null
            val href = link.attr("href").trim()
            if (!href.startsWith("/comic/")) return@mapNotNull null
            SManga.create().apply {
                url = href
                title = el.selectFirst(".comics-card__title h3, h3, .comics-card__title")?.text()?.trim()
                    ?.ifBlank { null }
                    ?: link.attr("title").trim().ifBlank { "?" }
                author = el.selectFirst("small.tags")?.text()?.trim()?.ifBlank { null }
                val img = el.selectFirst("amp-img, img")
                val src = (img?.attr("src") ?: img?.attr("data-src"))?.trim().orEmpty()
                thumbnail_url = if (src.isEmpty()) null else absolute(src)
            }
        }
        return MangasPage(mangas, hasNextPage = false)
    }

    // ---- Detay / bölümler --------------------------------------------------

    // Bölüm listesi yalnız section_slot parametresiyle sunucu tarafında render edilir.
    override fun mangaDetailsRequest(anime: SManga): Request {
        val target = absolute(anime.url).let {
            if (it.contains("section_slot=")) it else "$it?section_slot=0"
        }
        return Request.Builder().url(target).headers(headers).build()
    }

    override fun mangaDetailsParse(response: Response): SManga {
        val document = doc(response)
        return SManga.create().apply {
            url = response.request.url.encodedPath
            title = document.selectFirst("h1.comics-detail__title")?.text()?.trim()
                ?.ifBlank { null } ?: document.title().trim().ifBlank { "?" }
            author = document.selectFirst("h2.comics-detail__author")?.text()?.trim()?.ifBlank { null }
            genre = document.select("div.tag-list span.tag").joinToString(", ") { it.text().trim() }
                .ifBlank { null }
            description = document.selectFirst("p.comics-detail__desc")?.text()?.trim()
            val cover = document.selectFirst("div.pure-g div > amp-img, div.pure-g amp-img")
                ?.let { it.attr("src").ifBlank { it.attr("data-src") } }?.trim().orEmpty()
            thumbnail_url = if (cover.isEmpty()) null else absolute(cover)
            val tags = document.select("div.tag-list > span.tag, div.tag-list span.tag").map { it.text() }
            status = when {
                tags.any { it.contains("連載中") || it.contains("连载中") } -> SManga.ONGOING
                tags.any { it.contains("已完結") || it.contains("已完结") } -> SManga.COMPLETED
                else -> SManga.UNKNOWN
            }
        }
    }

    override fun chapterListRequest(manga: SManga): Request = mangaDetailsRequest(manga)

    override fun chapterListParse(response: Response): List<SChapter> {
        val document = doc(response)
        val updatedAt = parseUpdatedAt(document)
        return document.select("a.comics-chapters__item[href], .comics-chapters a[href]").mapNotNull { a ->
            val href = a.attr("href").trim()
            if (href.isEmpty()) return@mapNotNull null
            SChapter.create().apply {
                url = href
                name = a.text().trim().ifBlank { "Bölüm" }
                date_upload = updatedAt
                chapter_number = CH_NUM.find(a.text())?.groupValues?.get(1)?.toFloatOrNull() ?: -1f
            }
        }.distinctBy { it.url }
    }

    private fun parseUpdatedAt(document: Document): Long {
        val raw = document.selectFirst("em")?.text().orEmpty()
        if (!raw.contains("更新")) return 0L
        val cleaned = raw
            .replace("年", "-").replace("月", "-").replace("日", "")
            .replace(" 更新)", "").replace("更新", "")
            .replace("(", "").replace(")", "")
            .trim()
        return runCatching { DATE.parse(cleaned)?.time ?: 0L }.getOrDefault(0L)
    }

    // ---- Okuyucu -----------------------------------------------------------

    override fun pageListRequest(chapter: SChapter): Request =
        Request.Builder().url(absolute(chapter.url)).headers(headers).build()

    override fun pageListParse(response: Response): List<Page> {
        val pages = mutableListOf<String>()
        collectPages(response.body?.string().orEmpty(), pages, 0)
        return pages.distinct().mapIndexed { i, url -> Page(i, url, url) }
    }

    private fun collectPages(html: String, out: MutableList<String>, depth: Int) {
        if (html.isBlank()) return
        val document = Jsoup.parse(html)
        // 1) AMP durum JSON'u: her script bir sayfa.
        document.select("amp-state[id^=chapter][id$=Src] > script[type=application/json]").forEach { script ->
            val url = runCatching { JSONObject(script.data()).optString("url", "") }.getOrNull().orEmpty()
            if (url.startsWith("http")) out.add(url)
        }
        // 2) Yedek: amp-img/img data-src
        if (out.isEmpty()) {
            document.select("amp-img.comic-contain__item[data-src], img.comic-contain__item[data-src]")
                .forEach { img ->
                    val u = img.attr("data-src").trim()
                    if (u.startsWith("http")) out.add(u)
                }
        }
        // 3) Bölüm içi ek sayfa: yalnız "sonraki sayfa" bağlantısı (sonraki bölüm değil).
        if (depth < MAX_PAGE_HOPS) {
            val nextPage = document.select("div.next_chapter a").firstOrNull { a ->
                val t = a.text()
                t.contains("下一頁") || t.contains("下一页")
            }
            val nextHref = nextPage?.attr("href")?.trim().orEmpty()
            if (nextHref.startsWith("/comic/") || nextHref.startsWith("http")) {
                val target = absolute(nextHref).trimEnd('/') + "/last_chapter"
                val body = runCatching {
                    bypassCall(target).use { r -> if (r.isSuccessful) r.body?.string().orEmpty() else "" }
                }.getOrDefault("")
                if (body.isNotBlank()) collectPages(body, out, depth + 1)
            }
        }
    }

    /** `/last_chapter` istekleri app başlıkları + rastgele bypass hostuyla gider. */
    private fun bypassCall(target: String): Response {
        val path = runCatching { URI(target).path }.getOrDefault("")
        val bare = path.removeSuffix("/last_chapter")
        val host = BYPASS_HOSTS.random()
        val url = "https://$host/baozimhapp$bare"
        val req = Request.Builder().url(url).headers(appHeaders()).build()
        return client.newCall(req).execute()
    }

    private fun appHeaders(): Headers {
        val b = headers.newBuilder()
        b.set("referer", "https://app.baozimh.com/")
        b.set("app-id", "cn.sts.xiaoyun.ordermeals")
        b.set("app-version", "1.0.31")
        b.set("device-id", "BE2A.250530.026.F3")
        b.set("device-code", "2c712c6ba4e95a9f4157f94e1794a86c")
        b.set("user-agent", "baozimh_android/1.0.31/gb/adset")
        b.set("tsid", TSID)
        return b.build()
    }

    override fun imageUrlParse(response: Response): String = response.request.url.toString()

    /** Kapak: `topic_img` göreliyse statik kapak tabanına eklenir. */
    private fun coverOf(raw: String): String? {
        val v = raw.trim()
        if (v.isEmpty()) return null
        return when {
            v.startsWith("http://") || v.startsWith("https://") -> v
            v.startsWith("//") -> "https:$v"
            else -> COVER_BASE + v
        }
    }

    private fun absolute(u: String): String = when {
        u.startsWith("http://") || u.startsWith("https://") -> u
        u.startsWith("//") -> "https:$u"
        u.startsWith("/") -> baseUrl + u
        else -> "$baseUrl/$u"
    }

    private fun doc(response: Response): Document =
        Jsoup.parse(response.body?.string().orEmpty(), baseUrl)

    private companion object {
        const val MAX_PAGE_HOPS = 6
        const val COVER_BASE = "https://static-tw.baozimh.com/cover/"
        val CH_NUM = Regex("(\\d+(?:\\.\\d+)?)")
        val DATE = SimpleDateFormat("yyyy-MM-dd", Locale.ROOT)
        val BYPASS_HOSTS = listOf(
            "appgb-vdkr.baozimh.com",
            "appgb1-vdkr.baozimh.com",
            "appgb2-vdkr.baozimh.com",
            "app1.baozimh.com",
            "app2.baozimh.com",
            "app3.baozimh.com",
            "app4.baozimh.com",
        )
        const val TSID = "eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiJGcHFUQW1hTW9IM29EakdvZVRrZXBIbUZCc0h2SGtUVCIsImV4cGlyZSI6MjA3OTQ0MzE2Nywic3RhcnQiOjE3NjQwODMxNjd9.BlLrxNcpA747fEcAZKkExzqipbMXq-vmnZIll4ia1jg"
    }
}
