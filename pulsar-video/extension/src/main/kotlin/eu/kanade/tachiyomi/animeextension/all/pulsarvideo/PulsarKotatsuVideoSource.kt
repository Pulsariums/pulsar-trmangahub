package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import eu.kanade.tachiyomi.animesource.model.AnimeFilterList
import eu.kanade.tachiyomi.animesource.model.AnimesPage
import eu.kanade.tachiyomi.animesource.model.Hoster
import eu.kanade.tachiyomi.animesource.model.SAnime
import eu.kanade.tachiyomi.animesource.model.SEpisode
import eu.kanade.tachiyomi.animesource.model.Video
import eu.kanade.tachiyomi.animesource.online.AnimeHttpSource
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import org.skepsun.kototoro.parsers.ContentLoaderContext
import org.skepsun.kototoro.parsers.ContentParser
import org.skepsun.kototoro.parsers.InternalParsersApi
import org.skepsun.kototoro.parsers.bitmap.Bitmap
import org.skepsun.kototoro.parsers.config.ConfigKey
import org.skepsun.kototoro.parsers.config.ContentSourceConfig
import org.skepsun.kototoro.parsers.core.PagedContentParser
import org.skepsun.kototoro.parsers.model.Content
import org.skepsun.kototoro.parsers.model.ContentChapter
import org.skepsun.kototoro.parsers.model.ContentListFilter
import org.skepsun.kototoro.parsers.model.ContentParserSource
import org.skepsun.kototoro.parsers.model.ContentSource
import org.skepsun.kototoro.parsers.model.ContentState
import org.skepsun.kototoro.parsers.model.ContentType
import org.skepsun.kototoro.parsers.model.RATING_UNKNOWN
import org.skepsun.kototoro.parsers.model.SortOrder
import org.skepsun.kototoro.parsers.util.generateUid
import org.skepsun.kototoro.parsers.util.toAbsoluteUrl
import java.util.concurrent.ConcurrentHashMap

/**
 * kototoro-parsers `ContentParser` örneğini Aniyomi `AnimeHttpSource`'a bağlar.
 *
 * Manga tarafındaki `PulsarKotatsuSource` deseninin video eşi: kaynak verisi
 * APK'ya gömülü **kütüphaneden** gelir, biz yalnız köprüyü yazarız. Bir
 * ContentParser akışı:
 *
 *   getList(offset, order, filter) -> Content (liste)
 *   getDetails(content)            -> Content (bölümler dahil)
 *   getPages(chapter)              -> ContentPage (VIDEO: her sayfa bir video URL'si;
 *                                     doğrudan m3u8/mp4 ya da embed)
 *
 * Aniyomi v16 hoster tabanlı çalışır: `getHosterList(episode)` tek bir hoster
 * döndürür, `Hoster.videoList` içine tüm varyantlar (dil/embed) konur; host
 * `getVideoList(hoster)` çağırırsa aynı liste verilir.
 *
 * Parser örneği **lazy** kurulur (Nyora deseni): kaynak listesi açılırken
 * onlarca parser sınıfı yüklenmez.
 */
@OptIn(InternalParsersApi::class)
class PulsarKotatsuVideoSource(
    private val parserSource: ContentParserSource,
    override val lang: String,
) : AnimeHttpSource() {

    private val context = PulsarVideoLoaderContext()
    private val parser: ContentParser by lazy { context.newParserInstance(parserSource) }

    override val name: String = parserSource.title +
        if (parserSource.contentType == ContentType.HENTAI_VIDEO) " [18+]" else ""
    override val baseUrl: String by lazy { "https://" + parser.domain }
    override val supportsLatest: Boolean = true

    // ---- Liste -------------------------------------------------------------

    private fun pageStep(): Int = (parser as? PagedContentParser)?.pageSize ?: 30

    private suspend fun list(page: Int, order: SortOrder, query: String? = null): AnimesPage {
        val filter = if (query.isNullOrBlank()) {
            ContentListFilter.EMPTY
        } else {
            ContentListFilter(query = query)
        }
        // PagedContentParser offset'i kendi pageSize'iyle sayfaya çevirir;
        // offset daima pageSize'ın katı olmalı, yoksa sayfa atlanır.
        val entries = parser.getList((page - 1) * pageStep(), order, filter)
        return AnimesPage(entries.map { it.toSAnime() }, entries.isNotEmpty())
    }

    override suspend fun getPopularAnime(page: Int): AnimesPage =
        list(page, SortOrder.POPULARITY)

    override suspend fun getLatestUpdates(page: Int): AnimesPage =
        list(page, SortOrder.UPDATED)

    override fun getFilterList(): AnimeFilterList = AnimeFilterList()

    // Bu kaynaklarda sezon ayrımı yok; host çağırırsa boş döner.
    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getSeasonList(anime: SAnime): List<SAnime> = emptyList()

    override suspend fun getSearchAnime(
        page: Int,
        query: String,
        filters: AnimeFilterList,
    ): AnimesPage = if (query.isBlank()) {
        AnimesPage(emptyList(), false)
    } else {
        // Aramayi desteklemeyen parser istisna atar; bos sonuca cevrilir.
        runCatching { list(page, SortOrder.RELEVANCE, query) }
            .getOrElse { AnimesPage(emptyList(), false) }
    }

    // ---- Detay / bölümler --------------------------------------------------

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getAnimeDetails(anime: SAnime): SAnime =
        parser.getDetails(anime.toLib()).toSAnime()

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getEpisodeList(anime: SAnime): List<SEpisode> {
        val full = parser.getDetails(anime.toLib())
        // Kronolojik artan -> Mihon'un beklediği en-yeni-önce sırası.
        return (full.chapters ?: emptyList())
            .sortedBy { it.number }
            .asReversed()
            .map { it.toSEpisode() }
    }

    // ---- Video -------------------------------------------------------------

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getHosterList(episode: SEpisode): List<Hoster> {
        val pages = runCatching { parser.getPages(episode.toLibChapter()) }
            .getOrElse { return emptyList() }
        val videos = pages.mapNotNull { page ->
            val url = page.url.takeIf { it.startsWith("http") } ?: return@mapNotNull null
            val label = page.preview?.takeIf { it.isNotBlank() } ?: hostOf(url)
            val kind = if (isDirectStream(url)) "stream" else "embed"
            Video(url, "$label · $kind")
        }.sortedBy { if (isDirectStream(it.videoUrl)) 0 else 1 }
        if (videos.isEmpty()) return emptyList()
        return listOf(Hoster(hosterUrl = episode.url, hosterName = name, videoList = videos))
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getVideoList(hoster: Hoster): List<Video> = hoster.videoList.orEmpty()

    // ---- Aniyomi v16 ABI'sinin zorunlu Request/Parse iskeleti --------------
    // Veri parser'dan geldiği için ağ isteği üretilmez; suspend metotlar
    // yukarıda doğrudan override edildi. Host bu yardımcıları çağırmaz.

    override fun popularAnimeRequest(page: Int): Request = unsupportedRequest()
    override fun popularAnimeParse(response: Response): AnimesPage = unsupportedParse()
    override fun latestUpdatesRequest(page: Int): Request = unsupportedRequest()
    override fun latestUpdatesParse(response: Response): AnimesPage = unsupportedParse()
    override fun searchAnimeRequest(page: Int, query: String, filters: AnimeFilterList): Request =
        unsupportedRequest()
    override fun searchAnimeParse(response: Response): AnimesPage = unsupportedParse()
    override fun animeDetailsParse(response: Response): SAnime = unsupportedParse()
    override fun episodeListParse(response: Response): List<SEpisode> = unsupportedParse()
    override fun seasonListParse(response: Response): List<SAnime> = unsupportedParse()
    override fun hosterListParse(response: Response): List<Hoster> = unsupportedParse()

    private fun unsupportedRequest(): Request =
        throw UnsupportedOperationException("Pulsar parser kaynağı istek üretmez")

    private fun <T> unsupportedParse(): T =
        throw UnsupportedOperationException("Pulsar parser kaynağı yanıt ayrıştırmaz")

    private fun isDirectStream(url: String): Boolean {
        val path = url.substringBefore('?').lowercase()
        return path.endsWith(".m3u8") || path.endsWith(".mp4") || url.contains(".m3u8?")
    }

    private fun hostOf(url: String): String = runCatching {
        java.net.URI(url).host.orEmpty().removePrefix("www.")
    }.getOrNull().orEmpty().ifBlank { "video" }

    // ---- Dönüşümler --------------------------------------------------------

    private fun Content.toSAnime(): SAnime = SAnime.create().apply {
        url = this@toSAnime.url
        title = this@toSAnime.title
        thumbnail_url = this@toSAnime.largeCoverUrl ?: this@toSAnime.coverUrl
        description = this@toSAnime.description
        genre = this@toSAnime.tags.joinToString(", ") { it.title }.ifBlank { null }
        status = when (this@toSAnime.state) {
            ContentState.ONGOING -> SAnime.ONGOING
            ContentState.FINISHED -> SAnime.COMPLETED
            ContentState.ABANDONED -> SAnime.CANCELLED
            ContentState.PAUSED -> SAnime.ON_HIATUS
            else -> SAnime.UNKNOWN
        }
    }

    private fun SAnime.toLib(): Content {
        val absolute = url.toAbsoluteUrl(parser.domain)
        return Content(
            id = parser.generateUid(absolute),
            title = title,
            altTitles = emptySet(),
            url = url,
            // Parser detay isteğini publicUrl üzerinden kurar (AniWorld).
            publicUrl = absolute,
            rating = RATING_UNKNOWN,
            contentRating = null,
            coverUrl = thumbnail_url,
            tags = emptySet(),
            state = null,
            authors = emptySet(),
            source = parserSource,
        )
    }

    private fun ContentChapter.toSEpisode(): SEpisode = SEpisode.create().apply {
        url = this@toSEpisode.url
        name = this@toSEpisode.title?.takeIf { it.isNotBlank() }
            ?: "Episode ${this@toSEpisode.numberString() ?: ""}".trim()
        episode_number = episodeNumberFromUrl(this@toSEpisode.url) ?: this@toSEpisode.number
        date_upload = this@toSEpisode.uploadDate
        scanlator = this@toSEpisode.scanlator
    }

    private fun SEpisode.toLibChapter(): ContentChapter = ContentChapter(
        id = url.hashCode().toLong(),
        title = name,
        number = episode_number,
        volume = 0,
        url = url,
        scanlator = scanlator,
        uploadDate = date_upload,
        branch = null,
        source = parserSource,
    )

    private fun episodeNumberFromUrl(url: String): Float? =
        Regex("""(?:episode|ep)[-_/](\d+(?:[.-]\d+)?)""", RegexOption.IGNORE_CASE)
            .find(url)?.groupValues?.get(1)?.replace('-', '.')?.toFloatOrNull()
}

/**
 * ContentParser'ların beklediği [ContentLoaderContext] (Aniyomi hostunda
 * `MangaLoaderContext`'in karşılığı). Yalnız AniWorld/VIDEO parser'larının
 * kullandığı yüzey gerçek; WebView/Bitmap isteyen yollar bilinçli olarak
 * desteklenmiyor — o parser'lar zaten bu APK'da listelenmez.
 */
private class PulsarVideoLoaderContext : ContentLoaderContext() {

    override val cookieJar: CookieJar = MemoryCookieJar()

    override val httpClient: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    override fun newParserInstance(source: ContentSource): ContentParser {
        require(source is ContentParserSource) { "parser kaynağı değil: $source" }
        return KototoroParserFactory.newParser(source, this)
    }

    override fun newLinkResolver(link: HttpUrl): org.skepsun.kototoro.parsers.util.LinkResolver =
        throw UnsupportedOperationException("LinkResolver bu eklentide yok")

    override suspend fun evaluateJs(script: String): String? =
        throw UnsupportedOperationException("JavaScript bu eklentide yok")

    override suspend fun evaluateJs(baseUrl: String, script: String): String? =
        throw UnsupportedOperationException("JavaScript bu eklentide yok")

    override fun getConfig(source: ContentSource): ContentSourceConfig = DefaultConfig

    override fun getDefaultUserAgent(): String =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    override fun redrawImageResponse(
        response: Response,
        redraw: (Bitmap) -> Bitmap,
    ): Response = throw UnsupportedOperationException("Bitmap bu eklentide yok")

    override fun createBitmap(width: Int, height: Int): Bitmap =
        throw UnsupportedOperationException("Bitmap bu eklentide yok")

    private object DefaultConfig : ContentSourceConfig {
        override fun <T> get(key: ConfigKey<T>): T = key.defaultValue
    }
}

/**
 * KSP'nin ürettiği `ContentParserSource.newParser(context)` fonksiyonuna köprü.
 * Fonksiyon `internal` olduğu için Kotlin'den çağrılamaz; yansımayla çağrılır.
 * Böylece 40 parser sınıfı elle listelenmez, kütüphanenin kendi kayıt defteri
 * kullanılır.
 */
private object KototoroParserFactory {

    private val method by lazy {
        Class.forName("org.skepsun.kototoro.parsers.ContentParserFactoryKt")
            .methods
            .first { it.name == "newParser" && it.parameterCount == 2 }
    }

    fun newParser(source: ContentParserSource, context: ContentLoaderContext): ContentParser =
        method.invoke(null, source, context) as ContentParser
}

/** Süreç ömrü boyunca yaşayan basit bellek-içi cookie kavanozu. */
private class MemoryCookieJar : CookieJar {

    private val store = ConcurrentHashMap<String, MutableList<Cookie>>()

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val list = store.getOrPut(url.host) { mutableListOf() }
        synchronized(list) {
            for (cookie in cookies) {
                list.removeAll { it.name == cookie.name }
                list.add(cookie)
            }
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val list = store[url.host] ?: return emptyList()
        synchronized(list) {
            val now = System.currentTimeMillis()
            list.removeAll { it.expiresAt < now }
            return list.toList()
        }
    }
}
