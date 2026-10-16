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

    fun parseList(doc: Document, selector: String, baseUrl: String): List<ParsedManga> {
        val sel = selector.ifBlank { "div.bsx, div.manga-card, div.page-item-detail, div.manga" }
        return doc.select(sel).mapNotNull { el ->
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
    }

    fun parseChapters(doc: Document, selector: String, baseUrl: String): List<ParsedChapter> {
        val sel = selector.ifBlank { "div.chapter-item, li.wp-manga-chapter, div.eph-num, ul.clstyle li" }
        val chapterRegex = Regex("""(?:bolum|chapter|ch\.?|ep\.?)\s*[:#\-]?\s*(\d+(?:\.\d+)?)""", RegexOption.IGNORE_CASE)

        return doc.select(sel).mapIndexedNotNull { index, el ->
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
    }

    fun parsePages(doc: Document, selector: String, baseUrl: String): List<String> {
        val sel = selector.ifBlank { "div.page-break img, div#readerarea img, #init-manga-single-chapter img, div.reading-content img" }
        return doc.select(sel).mapNotNull { el ->
            val src = el.attr("data-src").ifBlank { null }
                ?: el.attr("data-lazy-src").ifBlank { null }
                ?: el.attr("src").ifBlank { null }
                ?: return@mapNotNull null

            val trimmed = src.trim()
            if (trimmed.startsWith("http")) trimmed else "$baseUrl/${trimmed.trimStart('/')}"
        }
    }
}
