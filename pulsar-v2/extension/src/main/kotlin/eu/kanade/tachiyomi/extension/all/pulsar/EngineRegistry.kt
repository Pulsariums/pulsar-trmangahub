package eu.kanade.tachiyomi.extension.all.pulsar

import org.jsoup.nodes.Document
import org.jsoup.nodes.Element

data class ParsedManga(
    val title: String,
    val url: String,
    val coverUrl: String?
)

data class ParsedChapter(
    val name: String,
    val url: String,
    val chapterNumber: Float,
    val dateUpload: Long
)

object EngineRegistry {

    // Modern siteler (Tailwind/Next.js) semantik sınıf kullanmıyor: kart
    // class'ı yok, linkler /manga/slug, /seri/slug, /series/slug, /manhwa/slug
    // biçiminde. Cihaz raporu "Liste boş" diyordu; sayfada 20-25 böyle link var.
    private val SLUG_SEGMENTS =
        setOf("manga", "seri", "series", "serie", "comic", "manhwa", "title", "title-detail", "webtoon")

    private fun genericList(doc: Document, baseUrl: String): List<ParsedManga> {
        val seen = LinkedHashMap<String, ParsedManga>()
        for (a in doc.select("a[href]")) {
            val raw = a.attr("href").trim()
            if (raw.isEmpty() || raw.startsWith("#")) continue
            val full = if (raw.startsWith("http")) raw else "$baseUrl/${raw.trimStart('/')}"
            val afterScheme = full.substringAfter("://", full)
            val path = afterScheme.substringAfter('/', "")
                .substringBefore('?').substringBefore('#').trim('/')
            val parts = path.split('/')
            if (parts.size != 2) continue
            if (parts[0].lowercase() !in SLUG_SEGMENTS) continue
            if (parts[1].length < 3) continue
            val key = full.substringBefore('?').trimEnd('/')
            if (seen.containsKey(key)) continue
            val title = a.text().trim()
                .ifBlank { a.selectFirst("img[alt]")?.attr("alt")?.trim().orEmpty() }
            if (title.length < 2) continue
            val img = a.selectFirst("img")
            val cover = img?.attr("data-src")?.ifBlank { null }
                ?: img?.attr("data-lazy-src")?.ifBlank { null }
                ?: img?.attr("src")?.ifBlank { null }
            seen[key] = ParsedManga(title = title, url = full, coverUrl = cover)
        }
        return seen.values.toList()
    }

    private val CHAPTER_HINT =
        Regex("""(?:bolum|bölüm|chapter|chap|ch)[-_ ]?(\d+(?:[.,]\d+)?)""", RegexOption.IGNORE_CASE)
    private val LEADING_NUMBER = Regex("""^(\d+(?:[.,]\d+)?)[-_ ]""")

    private fun genericChapters(doc: Document, baseUrl: String): List<ParsedChapter> {
        val seen = LinkedHashMap<String, ParsedChapter>()
        for (a in doc.select("a[href]")) {
            val raw = a.attr("href").trim()
            if (raw.isEmpty() || raw.startsWith("#")) continue
            val full = if (raw.startsWith("http")) raw else "$baseUrl/${raw.trimStart('/')}"
            val path = full.substringAfter("://", full).substringAfter('/', "")
                .substringBefore('?').substringBefore('#').trim('/')
            val parts = path.split('/')
            if (parts.size < 3) continue
            val last = parts.last().lowercase()
            val numText = CHAPTER_HINT.find(last)?.groupValues?.get(1)
                ?: LEADING_NUMBER.find(last)?.groupValues?.get(1)
                ?: continue
            val num = numText.replace(',', '.').toFloatOrNull() ?: continue
            val key = full.substringBefore('?').trimEnd('/')
            if (seen.containsKey(key)) continue
            val name = a.text().trim().ifBlank { parts.last() }
            seen[key] = ParsedChapter(name = name, url = full, chapterNumber = num, dateUpload = 0L)
        }
        return seen.values.toList()
    }

    private val PAGE_FILE = Regex("""/\d+(?:\.\d+)?\.(?:jpe?g|png|webp|avif)$""")

    private fun genericPages(doc: Document, baseUrl: String): List<String> {
        val seen = LinkedHashMap<String, String>()
        for (img in doc.select("img")) {
            val raw = img.attr("data-src").ifBlank { img.attr("data-lazy-src") }
                .ifBlank { img.attr("src") }.trim()
            if (raw.isEmpty()) continue
            val full = if (raw.startsWith("http")) raw else "$baseUrl/${raw.trimStart('/')}"
            val low = full.lowercase()
            if (low.contains("logo") || low.contains("icon") || low.contains("avatar") ||
                low.contains("banner") || low.contains("favicon")
            ) continue
            val alt = img.attr("alt").lowercase()
            val hinted = alt.contains("sayfa") || alt.contains("page") || PAGE_FILE.containsMatchIn(low)
            if (!hinted) continue
            seen[full] = full
        }
        return seen.keys.toList()
    }

    fun parseList(doc: Document, selector: String, baseUrl: String): List<ParsedManga> {
        val sel = selector.ifBlank { "div.bsx, div.manga-card, div.page-item-detail, div.manga" }
        val items = doc.select(sel).mapNotNull { el ->
            runCatching {
                val linkEl = el.selectFirst("a[href]") ?: return@runCatching null
                val rawUrl = linkEl.attr("href")
                val fullUrl = if (rawUrl.startsWith("http")) rawUrl else "$baseUrl/${rawUrl.trimStart('/')}"
                val title = el.selectFirst("h3, h2, h4, .title, a[title]")?.text()
                    ?: linkEl.attr("title").ifBlank { linkEl.text() }

                val imgEl = el.selectFirst("img[src], img[data-src], img[data-lazy-src]")
                val cover = imgEl?.attr("data-src")?.ifBlank { null }
                    ?: imgEl?.attr("data-lazy-src")?.ifBlank { null }
                    ?: imgEl?.attr("src")?.ifBlank { null }

                ParsedManga(title = title.trim(), url = fullUrl, coverUrl = cover)
            }.getOrNull()
        }
        return if (items.isNotEmpty()) items else genericList(doc, baseUrl)
    }

    fun parseChapters(doc: Document, selector: String, baseUrl: String): List<ParsedChapter> {
        val sel = selector.ifBlank { "div.chapter-item, li.wp-manga-chapter, div.eph-num, ul.clstyle li" }
        val chapterRegex = Regex("""(?:bolum|chapter|ch\.?|ep\.?)\s*[:#\-]?\s*(\d+(?:\.\d+)?)""", RegexOption.IGNORE_CASE)

        val items = doc.select(sel).mapIndexedNotNull { index, el ->
            runCatching {
                val linkEl = el.selectFirst("a[href]") ?: return@runCatching null
                val rawUrl = linkEl.attr("href")
                val fullUrl = if (rawUrl.startsWith("http")) rawUrl else "$baseUrl/${rawUrl.trimStart('/')}"
                val name = linkEl.text().ifBlank { el.text() }.trim()

                val num = chapterRegex.find(name)?.groupValues?.getOrNull(1)?.toFloatOrNull()
                    ?: (index + 1).toFloat()

                ParsedChapter(name = name, url = fullUrl, chapterNumber = num, dateUpload = 0L)
            }.getOrNull()
        }
        return if (items.isNotEmpty()) items else genericChapters(doc, baseUrl)
    }

    fun parsePages(doc: Document, selector: String, baseUrl: String): List<String> {
        val sel = selector.ifBlank { "div.page-break img, div#readerarea img, #init-manga-single-chapter img, div.reading-content img" }
        val items = doc.select(sel).mapNotNull { el ->
            val src = el.attr("data-src").ifBlank { null }
                ?: el.attr("data-lazy-src").ifBlank { null }
                ?: el.attr("src").ifBlank { null }
                ?: return@mapNotNull null

            val trimmed = src.trim()
            if (trimmed.startsWith("http")) trimmed else "$baseUrl/${trimmed.trimStart('/')}"
        }
        return if (items.isNotEmpty()) items else genericPages(doc, baseUrl)
    }
}
