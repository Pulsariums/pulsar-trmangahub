package eu.kanade.tachiyomi.extension.all.pulsar

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import org.json.JSONArray

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
            if (parts[1].lowercase() in JUNK_SLUGS) continue
            val key = full.substringBefore('?').trimEnd('/')
            if (seen.containsKey(key)) continue
            val title = a.text().trim()
                .ifBlank { a.selectFirst("img[alt]")?.attr("alt")?.trim().orEmpty() }
            if (title.length < 2) continue
            val cover = coverOf(a)
            seen[key] = ParsedManga(title = title, url = full, coverUrl = cover)
        }
        return seen.values.toList()
    }

    // Kart linkinin kendi içinde <img> yoksa en yakın 4 üst öğeye kadar bak.
    // WebtoonOku/koreli gibi sitelerde kapak, başlık linkinin kardeşi bir sarmalayıcıda durur.
    private fun coverOf(el: Element): String? {
        var cur: Element? = el
        var depth = 0
        while (cur != null && depth < 4) {
            val img = cur.selectFirst("img")
            if (img != null) {
                val cand = sequenceOf("data-src", "data-lazy-src", "src")
                    .map { img.attr(it).trim() }
                    .firstOrNull { it.isNotEmpty() && !it.startsWith("data:") }
                if (cand != null && !looksLikeBadge(cand)) return cand
            }
            cur = cur.parent()
            depth++
        }
        return null
    }

    private fun looksLikeBadge(url: String): Boolean {
        val l = url.lowercase()
        return l.contains("badge") || l.contains("placeholder") || l.contains("logo") || l.contains("icon")
    }

    private val CHAPTER_HINT =
        Regex("""(?:bolum|bölüm|chapter|chap|ch)[-_ ]?(\d+(?:[.,]\d+)?)""", RegexOption.IGNORE_CASE)
    private val CHAPTER_NUM = Regex("""^(\d+(?:[.,]\d+)?)(?:$|[-_].*)""")
    private val ASSET_PREFIXES = setOf("_next", "assets", "static", "images", "build", "_f", "wp-content", "uploads", "media")
    // Liste sayfalarında manga kartı gibi görünen ama manga olmayan yollar
    // (nabicix /manga/feed, webtoonoku /manhwa/feed, araznovel /series/feed…).
    private val JUNK_SLUGS = setOf(
        "feed", "list-mode", "list", "search", "request", "filter", "random",
        "genre", "tur", "kategori", "category", "page", "manga", "seri",
        "series", "manhwa", "comic", "webtoon",
    )
    private val CHAPTER_ROOTS = setOf("chapter", "bolum", "bölüm", "oku", "read", "episode")
    // Tek parçalı bölüm yolları: nabicix /<slug>-bolum-12/, webtoonoku /<slug>-chapter-50/.
    private fun oneSegmentPrefix(last: String): String? {
        if (!last.contains('-')) return null
        if (!CHAPTER_HINT.containsMatchIn(last)) return null
        return last.substringBefore("-chapter").substringBefore("-chap")
            .substringBefore("-bolum").substringBefore("-bölüm")
    }

    private fun genericChapters(doc: Document, baseUrl: String): List<ParsedChapter> {
        val byUrl = LinkedHashMap<String, ParsedChapter>()
        val prefixCount = LinkedHashMap<String, Int>()
        val urlPrefix = LinkedHashMap<String, String>()
        for (a in doc.select("a[href]")) {
            val raw = a.attr("href").trim()
            if (raw.isEmpty() || raw.startsWith("#")) continue
            val full = if (raw.startsWith("http")) raw else "$baseUrl/${raw.trimStart('/')}"
            val path = full.substringAfter("://", full).substringAfter('/', "")
                .substringBefore('?').substringBefore('#').trim('/')
            val parts = path.split('/')
            val twoSeg = parts.size == 2 && parts[0].lowercase() in CHAPTER_ROOTS
            val last = parts.last().lowercase()
            val oneSeg = oneSegmentPrefix(last)
            if (parts.size < 3 && !twoSeg && oneSeg == null) continue
            if (parts[0].lowercase() in ASSET_PREFIXES) continue
            val numText = CHAPTER_HINT.find(last)?.groupValues?.get(1)
                ?: CHAPTER_NUM.find(last)?.groupValues?.get(1)
            val num = numText?.replace(',', '.')?.toFloatOrNull() ?: if (twoSeg) 0f else continue
            val key = full.substringBefore('?').trimEnd('/')
            if (byUrl.containsKey(key)) continue
            val prefix = oneSeg ?: parts.dropLast(1).joinToString("/")
            val name = a.text().trim().ifBlank { parts.last() }
            byUrl[key] = ParsedChapter(name = name, url = full, chapterNumber = num, dateUpload = 0L)
            urlPrefix[key] = prefix
            prefixCount[prefix] = (prefixCount[prefix] ?: 0) + 1
        }
        val best = prefixCount.maxByOrNull { it.value }?.key ?: return emptyList()
        val picked = byUrl.entries.filter { urlPrefix[it.key] == best }.map { it.value }
        if (picked.none { it.chapterNumber == 0f }) return picked
        return picked.mapIndexed { i, ch ->
            if (ch.chapterNumber == 0f) ch.copy(chapterNumber = (i + 1).toFloat()) else ch
        }
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
            val file = low.substringAfterLast('/')
            val hinted = alt.contains("sayfa") || alt.contains("page") ||
                file.contains("page") || file.contains("sayfa") ||
                PAGE_FILE.containsMatchIn(low) ||
                Regex("""^\d{1,4}[._-]""").containsMatchIn(file)
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
        val sel = selector.ifBlank { "div.page-break img, div#readerarea img, #init-manga-single-chapter img, div.reading-content img, img[data-reader-page-image]" }
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

    // Bazı siteler sayfa görsellerini DOM'a koymuyor: inline `ts_reader.run` JSON'u
    // (nabicix), Qwik state (xcomic) gibi metin bloklarında duruyorlar. DOM'da aday
    // çıkmadığında ham HTML metninde mutlak/göreli görsel adresi arıyoruz.
    private val RAW_IMAGE = Regex(
        """(?:"|\\"|=)((?:https?://|/)[^\s"'\\<>()]+?\.(?:webp|jpe?g|png|avif))""",
        RegexOption.IGNORE_CASE,
    )

    fun rawImages(html: String, baseUrl: String): List<String> {
        val seen = LinkedHashMap<String, String>()
        for (m in RAW_IMAGE.findAll(html)) {
            val u = m.groupValues[1].trimEnd(',', ']', '}', ';', ')')
            val low = u.lowercase()
            if (low.contains("logo") || low.contains("icon") || low.contains("avatar") ||
                low.contains("banner") || low.contains("favicon") || low.contains("badge") ||
                low.contains("placeholder") || low.contains("theme")
            ) continue
            val file = low.substringAfterLast('/')
            val pageLike = file.contains("page") || file.contains("sayfa") ||
                Regex("""^\d{1,4}[._-]""").containsMatchIn(file) ||
                Regex("""/ch[_-]?\d+/""").containsMatchIn(low) ||
                Regex("""/manga_chapters?/""").containsMatchIn(low)
            if (!pageLike) continue
            val full = if (u.startsWith("http")) u else "$baseUrl/${u.trimStart('/')}"
            seen[full] = full
        }
        return seen.keys.toList()
    }

    // Bazı okuyucular görselleri DOM'a hiç koymuyor; adresler <script> içine gömülü
    // Qwik/TSR durumunda duruyor (nyxscans: displaySrc, xcomic: imageUrls). İki biçim:
    //  - urlField : "alan":"adres" çiftleri (anahtar tırnaklı ya da tırnaksız olabilir)
    //  - arrayName: "alan":[ ... ] dizisi; içindeki tırnaklı adresler
    fun scriptJsonPages(
        html: String,
        scriptSelector: String,
        urlField: String,
        arrayName: String,
        baseUrl: String,
        allowPattern: String = "",
        containsMarker: String = "",
    ): List<String> {
        if (scriptSelector.isBlank() || (urlField.isBlank() && arrayName.isBlank())) {
            return emptyList()
        }
        val allow = if (allowPattern.isBlank()) null else runCatching { Regex(allowPattern) }.getOrNull()
        val doc = Jsoup.parse(html, baseUrl)
        val out = LinkedHashSet<String>()
        for (script in doc.select(scriptSelector)) {
            val text = script.data().ifBlank { script.html() }
            if (containsMarker.isNotEmpty() && !text.contains(containsMarker)) continue
            if (text.isBlank()) continue
            if (urlField.isNotEmpty()) {
                val re = Regex(
                    "\"?${Regex.escape(urlField)}\"?\\s*:\\s*(?:\\\$R\\[\\d+\\]\\s*=\\s*)?\"([^\"]+)\"",
                )
                for (m in re.findAll(text)) addPageUrl(out, m.groupValues[1], allow)
            }
            if (arrayName.isNotEmpty()) {
                // İki biçim var: düz JSON `"alan":[...]` ve Qwik durum dizisi
                // `"alan",<tip>,[0,"adres",0,"adres",...]` (xcomic imageUrls).
                val head = Regex(
                    "\"?${Regex.escape(arrayName)}\"?\\s*(?::\\s*|,\\s*\\d+\\s*,\\s*)\\[([\\s\\S]*?)\\]",
                ).find(text)
                if (head != null) {
                    for (m in Regex("\"([^\"]+)\"").findAll(head.groupValues[1])) {
                        addPageUrl(out, m.groupValues[1], allow)
                    }
                }
            }
            if (out.size >= 500) break
        }
        return out.toList()
    }

    private val PAGE_URL_HINT = Regex("\\.(webp|jpg|jpeg|png|avif|gif)(\\?|$)", RegexOption.IGNORE_CASE)

    private fun addPageUrl(out: MutableSet<String>, raw: String, allow: Regex? = null) {
        val u = raw.trim().replace("\\/", "/")
        if (u.length < 8) return
        if (!u.startsWith("http") && !u.startsWith("/")) return
        val ok = PAGE_URL_HINT.containsMatchIn(u) || (allow != null && allow.containsMatchIn(u))
        if (!ok) return
        out.add(u)
    }

    // ---- Next.js RSC (self.__next_f.push) ---------------------------------
    // Slept Manga, Lunar Manga, Manga Ball gibi Next.js App Router siteleri
    // bölüm verisini HTML'e koymuyor; kaçışlı "flight" metnine gömüyor.
    // Burada o metni çıkarıp içindeki JSON dizilerini okuyoruz.
    private fun rscText(html: String): String {
        val marker = "self.__next_f.push([1,"
        val sb = StringBuilder()
        var i = html.indexOf(marker)
        while (i >= 0) {
            val start = html.indexOf('"', i + marker.length)
            if (start < 0) break
            var j = start + 1
            val out = StringBuilder()
            while (j < html.length) {
                val c = html[j]
                if (c == '\\' && j + 1 < html.length) {
                    when (val n = html[j + 1]) {
                        'n' -> out.append('\n')
                        't' -> out.append('\t')
                        'r' -> out.append('\r')
                        '"' -> out.append('"')
                        '\\' -> out.append('\\')
                        'u' -> if (j + 5 < html.length) {
                            out.append(html.substring(j + 2, j + 6).toIntOrNull(16)?.toChar() ?: ' ')
                            j += 4
                        }
                        else -> out.append(n)
                    }
                    j += 2
                } else if (c == '"') {
                    break
                } else {
                    out.append(c)
                    j++
                }
            }
            sb.append(out).append('\n')
            i = html.indexOf(marker, j)
        }
        return sb.toString()
    }

    /** "[başlangıç" konumundan itibaren dengeli JSON dizisini döndürür. */
    private fun balancedArray(text: String, start: Int): String? {
        var depth = 0
        var inStr = false
        var esc = false
        for (k in start until text.length) {
            val c = text[k]
            if (inStr) {
                if (esc) esc = false else if (c == '\\') esc = true else if (c == '"') inStr = false
            } else {
                when (c) {
                    '"' -> inStr = true
                    '[', '{' -> depth++
                    ']', '}' -> {
                        depth--
                        if (depth == 0) return text.substring(start, k + 1)
                    }
                }
            }
        }
        return null
    }

    private fun arrayAfter(text: String, key: String): JSONArray? {
        val needle = "\"$key\":["
        var i = text.indexOf(needle)
        while (i >= 0) {
            val start = i + needle.length - 1
            val body = balancedArray(text, start)
            if (body != null) {
                val arr = runCatching { JSONArray(body) }.getOrNull()
                if (arr != null && arr.length() > 0) return arr
            }
            i = text.indexOf(needle, i + 1)
        }
        return null
    }

    private fun numText(f: Float): String =
        if (f == f.toInt().toFloat()) f.toInt().toString() else f.toString()

    private fun jsonUnescape(s: String): String {
        if (!s.contains('\\')) return s
        val sb = StringBuilder()
        var i = 0
        while (i < s.length) {
            val c = s[i]
            if (c == '\\' && i + 1 < s.length) {
                when (s[i + 1]) {
                    'u' -> {
                        if (i + 5 < s.length) {
                            sb.append(s.substring(i + 2, i + 6).toIntOrNull(16)?.toChar() ?: ' ')
                            i += 6
                            continue
                        }
                        sb.append(s[i + 1])
                        i += 2
                    }
                    'n' -> { sb.append('\n'); i += 2 }
                    't' -> { sb.append('\t'); i += 2 }
                    'r' -> { sb.append('\r'); i += 2 }
                    '"' -> { sb.append('"'); i += 2 }
                    '\\' -> { sb.append('\\'); i += 2 }
                    '/' -> { sb.append('/'); i += 2 }
                    else -> { sb.append(s[i + 1]); i += 2 }
                }
            } else {
                sb.append(c)
                i++
            }
        }
        return sb.toString()
    }

    /**
     * Kartlar DOM'da <a> olarak yoksa RSC yükündeki siteUrl nesnelerinden üretir.
     * lunarx.to: {"title":{"romaji":…},"coverImage":{"large":…},"siteUrl":"/manga/<id>"}
     */
    fun rscList(html: String, baseUrl: String): List<ParsedManga> {
        val raw = rscText(html).replace("\\\"", "\"")
        if (!raw.contains("\"siteUrl\"")) return emptyList()
        val siteRe = Regex("\"siteUrl\":\"(/[^\"]+)\"")
        val titleRe = Regex("\"title\":\\{\"(?:romaji|english|native)\":\"((?:[^\"\\\\]|\\\\.)*)\"")
        val coverRe = Regex("\"coverImage\":\\{\"large\":\"((?:[^\"\\\\]|\\\\.)*)\"")
        val seen = LinkedHashMap<String, ParsedManga>()
        for (chunk in raw.split("{\"id\":\"")) {
            val site = siteRe.find(chunk)?.groupValues?.get(1) ?: continue
            if (!site.contains("/manga/")) continue
            val key = site
            if (seen.containsKey(key)) continue
            val title = titleRe.find(chunk)?.groupValues?.get(1)
                ?.let { jsonUnescape(it) }?.trim().orEmpty()
                .ifBlank { site.trimEnd('/').substringAfterLast('/') }
            val cover = coverRe.find(chunk)?.groupValues?.get(1)
                ?.let { jsonUnescape(it) }?.trim().orEmpty().ifBlank { null }
            seen[key] = ParsedManga(
                title = title,
                url = baseUrl.trimEnd('/') + site,
                coverUrl = cover,
            )
        }
        return seen.values.toList()
    }

    /**
     * RSC yükündeki "chapters" dizisinden bölüm üretir.
     * template: "/manga/{slug}/{number}" gibi; {slug} istek URL'sinin son parçası.
     */
    fun rscChapters(html: String, template: String, requestUrl: String): List<ParsedChapter> {
        if (template.isBlank()) return emptyList()
        val slug = requestUrl.substringBefore('?').substringBefore('#').trimEnd('/').substringAfterLast('/')
        val raw = rscText(html)
        if (raw.isEmpty()) return emptyList()
        val arr = arrayAfter(raw, "chapters") ?: arrayAfter(raw.replace("\\\"", "\""), "chapters")
            ?: return emptyList()
        val out = ArrayList<ParsedChapter>()
        for (i in 0 until arr.length()) {
            val o = arr.optJSONObject(i) ?: continue
            val number = (o.optString("number").ifBlank { o.optString("chapter_number") })
                .toFloatOrNull() ?: continue
            val name = o.optString("chapter_title").ifBlank { o.optString("chapterTitle") }
                .ifBlank { o.optString("name") }
                .ifBlank { "Bölüm " + numText(number) }
            val url = template.replace("{slug}", slug).replace("{number}", numText(number))
            out.add(ParsedChapter(name = name, url = url, chapterNumber = number, dateUpload = 0L))
        }
        return out
    }

    /** Bölüm listesi boş kaldığında cihaz raporuna sebebi taşıyan geçici tanı satırı. */
    fun diagnose(doc: Document, selector: String, baseUrl: String, html: String, code: Int, url: String): String {
        val sel = selector.ifBlank { "div.chapter-item, li.wp-manga-chapter, div.eph-num, ul.clstyle li" }
        val anchors = doc.select("a[href]")
        val sample = anchors.take(60)
            .map { it.attr("href") }
            .filter { it.isNotBlank() && !it.startsWith("#") }
            .joinToString(" ")
            .take(240)
        return "TANI kod=$code url=$url len=${html.length} a=${anchors.size} " +
            "sel=${doc.select(sel).size} gen=${genericChapters(doc, baseUrl).size} ilk=$sample"
    }
}
