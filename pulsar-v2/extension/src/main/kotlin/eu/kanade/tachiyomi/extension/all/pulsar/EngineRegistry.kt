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
        setOf("manga", "seri", "series", "serie", "comic", "comics", "manhwa", "title", "title-detail", "webtoon")

    // /en/manga/<slug>, /tr/seri/<slug> gibi dil onekli yollar.
    private val LOCALE_SEGMENT = Regex("""^[a-z]{2}(-[a-z]{2,4})?$""")

    // /series/comic/<slug> gibi tip parçalı yollar (kaynscan).
    private val TYPE_SEGMENTS =
        setOf("comic", "novel", "manga", "manhwa", "webtoon", "book")

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
            // Bazi siteler dili yol oneki olarak verir (/en/comic/<slug>).
            val trimmed = if (parts.size > 2 && LOCALE_SEGMENT.matches(parts[0].lowercase())) {
                parts.drop(1)
            } else {
                parts
            }
            val slugIdx: Int
            if (trimmed.size == 2 && trimmed[0].lowercase() in SLUG_SEGMENTS) {
                slugIdx = 1
            } else if (trimmed.size == 3 && trimmed[0].lowercase() in SLUG_SEGMENTS &&
                trimmed[1].lowercase() in TYPE_SEGMENTS
            ) {
                slugIdx = 2
            } else {
                continue
            }
            if (trimmed[slugIdx].length < 3) continue
            if (trimmed[slugIdx].lowercase() in JUNK_SLUGS) continue
            val key = full.substringBefore('?').trimEnd('/')
            if (seen.containsKey(key)) continue
            val title = a.text().trim()
                .ifBlank { a.selectFirst("img[alt]")?.attr("alt")?.trim().orEmpty() }
            if (title.length < 2) continue
            val cover = absoluteUrl(coverOf(a), baseUrl)
            seen[key] = ParsedManga(title = title, url = full, coverUrl = cover)
        }
        return seen.values.toList()
    }

    private fun absoluteUrl(u: String?, baseUrl: String): String {
        if (u.isNullOrBlank()) return ""
        if (u.startsWith("http")) return u
        if (u.startsWith("//")) return "https:$u"
        return baseUrl.trimEnd('/') + "/" + u.trimStart('/')
    }

    // Kart linkinin kendi içinde <img> yoksa en yakın 4 üst öğeye kadar bak.
    // WebtoonOku/koreli gibi sitelerde kapak, başlık linkinin kardeşi bir sarmalayıcıda durur.
    private fun coverOf(el: Element): String? {
        var cur: Element? = el
        var depth = 0
        while (cur != null && depth < 4) {
            val img = cur.selectFirst("img")
            if (img != null) {
                val cand = sequenceOf(
                    "data-src", "data-lazy-src", "data-original", "data-lzl-src",
                    "data-cc-src", "data-default-src", "src",
                )
                    .map { img.attr(it).trim() }
                    .firstOrNull { it.isNotEmpty() && !it.startsWith("data:") }
                    ?: img.attr("srcset").substringBefore(' ').trim().ifEmpty { null }
                if (cand != null && looksLikeUrl(cand) && !looksLikeBadge(cand)) return cand
            }
            // Bazi temalar gorseli data-bg attribute'unda tutar (manhwa18).
            cur.attr("data-bg").trim().takeIf { it.isNotEmpty() }?.let { return it }
            // Bazi temalar kapagi <img> yerine CSS background-image ile verir.
            backgroundImage(cur)?.let { if (!looksLikeBadge(it)) return it }
            cur.selectFirst("[style*=background-image]")?.let { node ->
                backgroundImage(node)?.let { if (!looksLikeBadge(it)) return it }
            }
            cur.selectFirst("[data-bg]")?.attr("data-bg")?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
            cur = cur.parent()
            depth++
        }
        return null
    }

    private fun backgroundImage(el: Element): String? {
        val style = el.attr("style")
        if (!style.contains("background-image", ignoreCase = true)) return null
        val m = Regex("""url\(\s*['"]?([^'")]+)['"]?\s*\)""").find(style) ?: return null
        return m.groupValues[1].trim().ifEmpty { null }
    }

    // data-* alanlari bazen URL degil bayrak olur (Next.js data-nimg="1").
    private fun looksLikeUrl(value: String): Boolean {
        val v = value.trim()
        if (v.length < 8) return false
        if (v.startsWith("http") || v.startsWith("//") || v.startsWith("/")) return true
        return v.contains('/') && (v.contains(".jpg") || v.contains(".jpeg") || v.contains(".png") ||
            v.contains(".webp") || v.contains(".avif") || v.contains(".gif"))
    }

    private fun looksLikeBadge(url: String): Boolean {
        val l = url.lowercase()
        if (l.contains("badge") || l.contains("placeholder")) return true
        // "logo"/"icon" yalnız DOSYA ADINDA rozet sayılır: niadd kapakları
        // .../<dil>_manga/logo/<kapak>.jpg yolundan geliyor ve yanlışlıkla eleniyordu.
        val dosya = l.substringAfterLast('/').substringBefore('?').substringBefore('#')
        return dosya.contains("logo") || dosya.contains("icon")
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
                // Seçici doğrudan <a href> eşleştirebilir (ör. okutoon a.update-card-cover);
                // Jsoup'un alt öğe araması kendini bulamaz, o yüzden önce kendine bakılır.
                val linkEl = if (el.tagName() == "a" && el.hasAttr("href")) el else el.selectFirst("a[href]")
                linkEl ?: return@runCatching null
                val rawUrl = linkEl.attr("href")
                val fullUrl = if (rawUrl.startsWith("http")) rawUrl else "$baseUrl/${rawUrl.trimStart('/')}"
                // Kapak bağlantılarında metin boştur; başlık aria-label veya img alt'ta durur.
                val title = el.selectFirst("h3, h2, h4, .title, a[title]")?.text()?.trim().orEmpty()
                    .ifBlank { linkEl.attr("title") }
                    .ifBlank { linkEl.attr("aria-label") }
                    .ifBlank { linkEl.text() }
                    .ifBlank { el.selectFirst("img[alt]")?.attr("alt").orEmpty() }
                    .trim()

                // Karttaki ilk <img> çoğu temada "manhwa.png" tür rozeti veya
                // data: yer tutucusudur. Rozeti ve data: URL'yi atla; kapağı
                // gerçek adresten al ve göreliyse mutlaklaştır.
                // Kapak çıkarımı tek yerde: coverOf data-original/data-bg/srcset/
                // background-image zincirini de geziyor ve 4 üst öğeye kadar iniyor.
                val cover = coverOf(el)?.let { raw ->
                    val u = raw.trim()
                    when {
                        u.startsWith("http") -> u
                        u.startsWith("//") -> "https:$u"
                        else -> "$baseUrl/${u.trimStart('/')}"
                    }
                }

                ParsedManga(title = title.trim(), url = fullUrl, coverUrl = cover)
            }.getOrNull()
        }
        return if (items.isNotEmpty()) items else genericList(doc, baseUrl)
    }

    fun parseChapters(doc: Document, selector: String, baseUrl: String): List<ParsedChapter> {
        val sel = selector.ifBlank { "div.chapter-item, li.wp-manga-chapter, div.eph-num, ul.clstyle li" }
        val chapterRegex = Regex(
            """(?:bolum|chapter|ch\.?|ep\.?)\s*[:#\-]?\s*(\d+(?:\.\d+)?)|#\s*(\d+(?:\.\d+)?)""",
            RegexOption.IGNORE_CASE,
        )

        val items = doc.select(sel).mapIndexedNotNull { index, el ->
            runCatching {
                // Seçici doğrudan bölüm bağlantısını eşleştirebilir (a.chapter-box).
                // Jsoup'un alt öğe araması kendini bulmaz; önce kendine bakılır.
                val linkEl = if (el.tagName() == "a" && el.hasAttr("href")) {
                    el
                } else {
                    el.selectFirst("a[href]")
                }
                linkEl ?: return@runCatching null
                val rawUrl = linkEl.attr("href")
                val fullUrl = if (rawUrl.startsWith("http")) rawUrl else "$baseUrl/${rawUrl.trimStart('/')}"
                // Kart bağlantılarında metin boş olabiliyor; ad aria-label/title'da durur.
                val name = linkEl.text().ifBlank { linkEl.attr("aria-label") }
                    .ifBlank { linkEl.attr("title") }.ifBlank { el.text() }.trim()

                val match = chapterRegex.find(name)
                val num = (match?.groupValues?.getOrNull(1)?.takeIf { it.isNotBlank() }
                    ?: match?.groupValues?.getOrNull(2))?.toFloatOrNull()
                    ?: (index + 1).toFloat()

                ParsedChapter(name = name, url = fullUrl, chapterNumber = num, dateUpload = 0L)
            }.getOrNull()
        }
        return if (items.isNotEmpty()) items else genericChapters(doc, baseUrl)
    }

    fun parsePages(
        doc: Document,
        selector: String,
        baseUrl: String,
        pageUrlTemplate: String = "",
    ): List<String> {
        val sel = selector.ifBlank { "div.page-break img, div#readerarea img, #init-manga-single-chapter img, div.reading-content img, img[data-reader-page-image], link[rel=\"preload\"][as=\"fetch\"]" }
        val items = doc.select(sel).mapNotNull { el ->
            val uid = el.attr("uid").trim().ifBlank { null }
            val raw = el.attr("data-src").ifBlank { null }
                ?: el.attr("data-lazy-src").ifBlank { null }
                ?: el.attr("data-original").ifBlank { null }
                ?: el.attr("src").ifBlank { null }
                ?: el.attr("href").ifBlank { null }
            val src = raw?.trim()

            // comic-days: sayfa adresi <link rel="preload" as="fetch" href="...">.
            // erisscans: <img src=placeholder uid="...">; gercek adres nitelikte yok.
            if (src == null || src.startsWith("data:") || src == "#" ||
                src.contains("placeholder", ignoreCase = true)
            ) {
                // uid'den URL UYDURMA: yalniz sunucu sablonu varsa {uid} doldur,
                // yoksa sayfayi atla (yanlis sayfa uretmekten iyidir).
                if (uid == null || pageUrlTemplate.isBlank()) return@mapNotNull null
                return@mapNotNull pageUrlTemplate.replace("{uid}", uid)
            }

            if (src.startsWith("http")) src else "$baseUrl/${src.trimStart('/')}"
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
                // mangaball: .../<hash>-001.webp — sayfa numarası dosya adının sonunda.
                Regex("""[-_]\d{1,4}\.(?:webp|jpe?g|png|avif)$""").containsMatchIn(file) ||
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
        urlBase: String = "",
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
                for (m in re.findAll(text)) addPageUrl(out, m.groupValues[1], allow, urlBase)
            }
            if (arrayName.isNotEmpty()) {
                // İki biçim var: düz JSON `"alan":[...]` ve Qwik durum dizisi
                // `"alan",<tip>,[0,"adres",0,"adres",...]` (xcomic imageUrls).
                val head = Regex(
                    "\"?${Regex.escape(arrayName)}\"?\\s*(?::\\s*|=\\s*|,\\s*\\d+\\s*,\\s*)\\[([\\s\\S]*?)\\]",
                ).find(text)
                if (head != null) {
                    for (m in Regex("[\"']([^\"']+)[\"']").findAll(head.groupValues[1])) {
                        addPageUrl(out, m.groupValues[1], allow, urlBase)
                    }
                }
            }
            if (out.size >= 500) break
        }
        return out.toList()
    }

    private val PAGE_URL_HINT = Regex("\\.(webp|jpg|jpeg|png|avif|gif)(\\?|$)", RegexOption.IGNORE_CASE)

    private fun addPageUrl(out: MutableSet<String>, raw: String, allow: Regex? = null, urlBase: String = "") {
        val rawUrl = raw.trim().replace("\\/", "/")
        if (rawUrl.length < 8) return
        val u = when {
            rawUrl.startsWith("http") -> rawUrl
            urlBase.isBlank() -> rawUrl
            rawUrl.startsWith("/") -> urlBase.trimEnd('/') + rawUrl
            else -> urlBase.trimEnd('/') + "/" + rawUrl.trimStart('/')
        }
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

    // Nyx Scans gibi siteler bölüm listesini DOM'a değil gömülü RSC/Qwik durumuna
    // yazıyor: initialChapters:$R[73]=[$R[74]={slug:"chapter-60",number:60,...}, ...].
    // URL şablonu {series} ve {slug} yer tutucularını taşır.
    fun scriptJsonChapters(
        html: String,
        scriptSelector: String,
        containsMarker: String,
        arrayName: String,
        urlTemplate: String,
        series: String,
        baseUrl: String,
        slugField: String = "slug",
        numberField: String = "number",
    ): List<ParsedChapter> {
        if (scriptSelector.isBlank() || arrayName.isBlank() || urlTemplate.isBlank()) {
            return emptyList()
        }
        val doc = Jsoup.parse(html, baseUrl)
        val out = ArrayList<ParsedChapter>()
        for (script in doc.select(scriptSelector)) {
            val text = script.data().ifBlank { script.html() }
            if (text.isBlank()) continue
            if (containsMarker.isNotEmpty() && !text.contains(containsMarker)) continue
            // RSC'de dizi başlığı "$R[73]=" önekiyle gelir: initialChapters:$R[73]=[...]
            val head = Regex(
                "\"?${Regex.escape(arrayName)}\"?\\s*(?::\\s*|=\\s*)(?:\\\$R\\[\\d+\\]\\s*=\\s*)?\\[",
            ).find(text) ?: continue
            val from = head.range.last + 1
            // Elemanlar $R[n]={...} referansları ve iç içe diziler taşır; "ilk ]" ile
            // kesmek listeyi eksik bırakıyordu (nyx: 60 bölümün 0'ı). Derinlik sayılır.
            var depth = 1
            var idx = from
            var inString = false
            var escaped = false
            while (idx < text.length) {
                val c = text[idx]
                if (inString) {
                    if (escaped) {
                        escaped = false
                    } else if (c == '\\') {
                        escaped = true
                    } else if (c == '"') {
                        inString = false
                    }
                } else {
                    when (c) {
                        '"' -> inString = true
                        '[' -> depth++
                        ']' -> {
                            depth--
                            if (depth == 0) break
                        }
                    }
                }
                idx++
            }
            val region = text.substring(from, idx.coerceAtMost(text.length))
            val slugs = Regex("\"?${Regex.escape(slugField)}\"?\\s*:\\s*\"([^\"]+)\"").findAll(region)
                .map { it.groupValues[1] }.toList()
            val numbers = Regex(
                "\"?${Regex.escape(numberField)}\"?\\s*:\\s*(?:\\\$R\\[\\d+\\]\\s*=\\s*)?(\\d+(?:\\.\\d+)?)",
            ).findAll(region).map { it.groupValues[1] }.toList()
            for (i in slugs.indices) {
                val slug = slugs[i]
                val num = numbers.getOrNull(i)?.toFloatOrNull() ?: 0f
                val url = urlTemplate.replace("{series}", series).replace("{slug}", slug).replace("{number}", numText(num))
                out.add(ParsedChapter(name = "Bölüm " + numText(num), url = url, chapterNumber = num, dateUpload = 0L))
            }
            if (out.isNotEmpty()) break
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
