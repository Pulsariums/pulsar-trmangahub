package eu.kanade.tachiyomi.extension.all.pulsar

import eu.kanade.tachiyomi.source.model.FilterList
import eu.kanade.tachiyomi.source.model.MangasPage
import eu.kanade.tachiyomi.source.model.Page
import eu.kanade.tachiyomi.source.model.SChapter
import eu.kanade.tachiyomi.source.model.SManga
import eu.kanade.tachiyomi.source.model.SMangaUpdate
import eu.kanade.tachiyomi.source.online.HttpSource
import okhttp3.OkHttpClient
import okhttp3.Request
import org.koitharu.kotatsu.parsers.MangaParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.model.MangaState
import org.koitharu.kotatsu.parsers.model.SortOrder
import org.koitharu.kotatsu.parsers.util.toAbsoluteUrl
import org.koitharu.kotatsu.parsers.model.Manga as LibManga
import org.koitharu.kotatsu.parsers.model.MangaChapter as LibChapter
import org.koitharu.kotatsu.parsers.model.MangaListFilter as LibFilter
import org.koitharu.kotatsu.parsers.model.MangaPage as LibPage

private const val PAGE_STEP = 20

private val CHAPTER_PATTERNS = listOf(
    Regex("""(?:chapter|chap|ch\.?|episode|ep\.?)\s*[:#\-]?\s*(\d+(?:\.\d+)?)""", RegexOption.IGNORE_CASE),
    Regex("""第\s*(\d+(?:\.\d+)?)\s*(?:话|話|章|回)""", RegexOption.IGNORE_CASE),
    Regex("""(?:^|\s)(\d+(?:\.\d+)?)\s*(?:화|話|话|章|回)(?:\s|$)""", RegexOption.IGNORE_CASE),
)

/**
 * kotatsu-parsers enum girdisini Mihon HttpSource'a bağlayan köprü
 * (NyoraLocalSource örüntüsü — bölüm sırası normalizasyonu, lazy parser,
 * MangaEclipse absolutize düzeltmesi ve WebView tabanlı CF çözümlemesi dahil).
 */
class PulsarKotatsuSource(
    private val parserSource: MangaParserSource,
    override val lang: String,
) : HttpSource() {

    override val name: String =
        PulsarPatches.TITLE_OVERRIDES[parserSource.name] ?: parserSource.title.ifBlank { parserSource.name }
    override val supportsLatest = true

    /**
     * Parser'lara verilen istemci. Otelin `network.client`'i tek basina DoH/TLS
     * katmani tasimiyor; bu yuzden manga motoru (PulsarSource) ile ayni yigdiz:
     * sistem DNS -> DoH yedegi, TLS reset/trust-anchor yakalayan interceptor,
     * parcali ClientHello. 2026-11-23: video tarafinda ayni duzeltme 10 kaynagi
     * "liste bos/reset/trust-anchor" sinifindan cikardi.
     */
    private val networkClient: OkHttpClient by lazy { buildClient(preferDoh = false) }

    /** Yedek istemci: DoH-oncelikli + parcali; bos sonuc/istisna tekrarinda kullanilir. */
    private val cleanClient: OkHttpClient by lazy { buildClient(preferDoh = true) }

    private val context by lazy { PulsarContext(networkClient) }
    private val parser by lazy { context.newParserInstance(parserSource).also { context.bindParser(it) } }

    private val cleanContext by lazy { PulsarContext(cleanClient) }
    private val cleanParser by lazy {
        cleanContext.newParserInstance(parserSource).also { cleanContext.bindParser(it) }
    }

    @Volatile
    private var useClean = false

    private fun activeParser() = if (useClean) cleanParser else parser

    private fun buildClient(preferDoh: Boolean): OkHttpClient {
        val base = network.client.newBuilder()
            .followRedirects(true)
            .followSslRedirects(true)
            .dns(PulsarSource.DohFallbackDns(null, preferDoh))
            .build()
        val trust = defaultTrustManager() ?: return base
        if (preferDoh) {
            return base.newBuilder()
                .sslSocketFactory(TlsFragmentingSocketFactory(), trust)
                .build()
        }
        val fragmenting = base.newBuilder()
            .dns(PulsarSource.DohFallbackDns(null, preferDoh = true))
            .sslSocketFactory(TlsFragmentingSocketFactory(), trust)
            .build()
        return base.newBuilder()
            .addInterceptor(PulsarSource.TlsRetryInterceptor(fragmenting))
            .build()
    }

    private fun defaultTrustManager(): javax.net.ssl.X509TrustManager? = runCatching {
        val f = javax.net.ssl.TrustManagerFactory
            .getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm())
        f.init(null as java.security.KeyStore?)
        f.trustManagers.filterIsInstance<javax.net.ssl.X509TrustManager>().firstOrNull()
    }.getOrNull()

    override val baseUrl by lazy { runCatching { "https://" + activeParser().domain }.getOrDefault("") }
    override val client get() = if (useClean) cleanContext.httpClient else context.httpClient

    /**
     * Parser cagrisini yurutur; sonuc bos ya da istisna ise ayni cagri DoH-oncelikli
     * istemciyle bir kez tekrarlanir. Basariliysa kaynak yedek istemciye sabitlenir.
     */
    private suspend fun <T> parserCall(
        empty: (T) -> Boolean,
        block: suspend (MangaParser) -> T,
    ): T {
        if (useClean) return block(cleanParser)
        val first = try {
            block(parser)
        } catch (e: Exception) {
            val retried = block(cleanParser)
            useClean = true
            return retried
        }
        if (!empty(first)) return first
        val retried = block(cleanParser)
        if (!empty(retried)) useClean = true
        return retried
    }

    private suspend fun list(page: Int, order: SortOrder, query: String?): MangasPage {
        val filter = if (query.isNullOrBlank()) LibFilter.EMPTY else LibFilter(query = query)
        val entries = parserCall(empty = { it.isEmpty() }) { p ->
            p.getList((page - 1) * PAGE_STEP, order, filter)
        }
        return MangasPage(entries.map { it.toSManga() }, hasNextPage = entries.isNotEmpty())
    }

    override suspend fun getPopularManga(page: Int): MangasPage = list(page, SortOrder.POPULARITY, null)
    override suspend fun getLatestUpdates(page: Int): MangasPage = list(page, SortOrder.UPDATED, null)
    // Bazi parser'lar aramayi desteklemiyor (SEARCH_NOT_SUPPORTED) ya da en az 3 karakter istiyor (ComicK/HoneyManga); istisna yerine bos sonuc donuyoruz.
    // Kototoro kaynak testi aramayi zorunlu adim sayiyor: parser'in aramasi bos
    // donerse populer liste cekilip baslikta yerel filtre uygulanir (video ile ayni).
    override suspend fun getSearchManga(page: Int, query: String, filters: FilterList): MangasPage {
        if (query.isBlank()) return MangasPage(emptyList(), hasNextPage = false)
        val direct = runCatching { list(page, SortOrder.RELEVANCE, query) }.getOrNull()
        if (direct != null && direct.mangas.isNotEmpty()) return direct
        val popular = runCatching { list(page, SortOrder.POPULARITY, null) }.getOrNull()
            ?: return MangasPage(emptyList(), hasNextPage = false)
        val needle = query.trim().lowercase()
        return MangasPage(
            popular.mangas.filter { it.title.lowercase().contains(needle) },
            hasNextPage = false,
        )
    }

    override suspend fun getMangaUpdate(
        manga: SManga,
        chapters: List<SChapter>,
        fetchDetails: Boolean,
        fetchChapters: Boolean,
    ): SMangaUpdate {
        val full = parserCall(empty = { false }) { p -> p.getDetails(manga.toLib()) }
        return SMangaUpdate(
            manga = full.toSManga(),
            chapters = (full.chapters ?: emptyList()).toMihonChapters(),
        )
    }

    // Bölüm sırası Nyora düzeltmesi: kotatsu sırası site-başına değişken; Mihon
    // index 0'ı EN YENİ sayar. Gerçek kronolojik sıra bölüm numaralarından
    // türetilir, sonra newest-first'e çevrilir (asc/desc bug'ı bu yüzden çıkmaz).
    private fun List<LibChapter>.toMihonChapters(): List<SChapter> {
        if (isEmpty()) return emptyList()
        val keys = mapIndexed { i, c -> ChKey(c, chapterNumberOf(c.title, c.number), i) }
        val chronological = when {
            keys.count { it.number != null } >= 2 -> keys.sortedWith(
                compareBy(
                    { it.ch.volume.takeIf { v -> v > 0 } ?: 0 },
                    { it.number ?: Float.MAX_VALUE },
                    { it.ch.uploadDate.takeIf { d -> d > 0L } ?: Long.MAX_VALUE },
                    { it.index },
                ),
            )
            keys.count { it.ch.uploadDate > 0L } >= 2 -> keys.sortedWith(
                compareBy(
                    { it.ch.uploadDate.takeIf { d -> d > 0L } ?: Long.MAX_VALUE },
                    { it.index },
                ),
            )
            else -> keys
        }
        val newestFirst = chronological.asReversed()
        return newestFirst.mapIndexed { i, k ->
            k.ch.toSChapter(number = k.number ?: (newestFirst.size - i).toFloat())
        }
    }

    private class ChKey(val ch: LibChapter, val number: Float?, val index: Int)

    private fun chapterNumberOf(title: String?, parserNumber: Float): Float? =
        title.parseChapterNumber() ?: parserNumber.takeIf { it > 0f }

    private fun String?.parseChapterNumber(): Float? {
        val value = this?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        CHAPTER_PATTERNS.firstNotNullOfOrNull { it.find(value)?.groupValues?.getOrNull(1)?.toFloatOrNull() }
            ?.let { return it }
        return value.toFloatOrNull()
    }

    override suspend fun getPageList(chapter: SChapter): List<Page> {
        val lib = LibChapter(
            id = chapter.url.hashCode().toLong(),
            title = chapter.name, number = chapter.chapter_number, volume = 0,
            url = chapter.url, scanlator = chapter.scanlator, uploadDate = 0, branch = null,
            source = parserSource,
        )
        val pages = parserCall(empty = { it.isEmpty() }) { p -> p.getPages(lib) }
        return pages.mapIndexed { i, p ->
            val raw = p.url.ifBlank { activeParser().getPageUrl(p) }
            Page(i, "", raw.toAbsoluteUrl(activeParser().domain))
        }
    }

    override fun imageUrlParse(response: okhttp3.Response): String = throw UnsupportedOperationException()
    override suspend fun getImageUrl(page: Page): String = page.imageUrl ?: ""

    private fun LibManga.toSManga() = SManga.create().also { s ->
        s.url = url
        s.title = title
        s.thumbnail_url = largeCoverUrl ?: coverUrl
        s.author = authors.joinToString().ifBlank { null }
        s.description = description
        s.genre = tags.joinToString { it.title }
        s.status = when (state) {
            MangaState.ONGOING -> SManga.ONGOING
            MangaState.FINISHED -> SManga.COMPLETED
            MangaState.ABANDONED -> SManga.CANCELLED
            MangaState.PAUSED -> SManga.ON_HIATUS
            else -> SManga.UNKNOWN
        }
    }

    private fun SManga.toLib() = LibManga(
        id = url.hashCode().toLong(), title = title, altTitles = emptySet(), url = url,
        // Parser detay istegini publicUrl uzerinden kuruyor (InManga/Prochan); goreli url "Expected URL scheme" atiyor.
        publicUrl = url.toAbsoluteUrl(parser.domain), rating = -1f, contentRating = null, coverUrl = thumbnail_url,
        tags = emptySet(), state = null, authors = emptySet(), source = parserSource,
    )

    private fun LibChapter.toSChapter(number: Float) = SChapter.create().also { c ->
        c.url = url
        c.chapter_number = number
        c.name = title?.takeIf { it.isNotBlank() }
            ?: if (number > 0f) "Chapter ${number.asChapterLabel()}" else "Chapter"
        c.scanlator = scanlator
        c.date_upload = uploadDate
    }

    private fun Float.asChapterLabel(): String =
        if (this % 1f == 0f) toInt().toString() else toString()

    override fun popularMangaRequest(page: Int): Request = throw UnsupportedOperationException()
    override fun popularMangaParse(response: okhttp3.Response): MangasPage = throw UnsupportedOperationException()
    override fun searchMangaRequest(page: Int, query: String, filters: FilterList): Request = throw UnsupportedOperationException()
    override fun searchMangaParse(response: okhttp3.Response): MangasPage = throw UnsupportedOperationException()
    override fun latestUpdatesRequest(page: Int): Request = throw UnsupportedOperationException()
    override fun latestUpdatesParse(response: okhttp3.Response): MangasPage = throw UnsupportedOperationException()
    override fun mangaDetailsParse(response: okhttp3.Response): SManga = throw UnsupportedOperationException()
    override fun chapterListParse(response: okhttp3.Response): List<SChapter> = throw UnsupportedOperationException()
    override fun pageListParse(response: okhttp3.Response): List<Page> = throw UnsupportedOperationException()

    override val id: Long by lazy {
        val key = "pulsar-kotatsu/${parserSource.name}/$lang"
        var h = 1125899906842597L
        for (ch in key) h = 31 * h + ch.code
        h and Long.MAX_VALUE
    }
}
