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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withTimeoutOrNull
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

    private val cookieJar = MemoryCookieJar()

    /**
     * Parser'lara verilecek istemci. PulsarVideoSource ile aynı ağ katmanı:
     * DoH yedeği (sistem DNS'i çözmezse), TLS reset/trust-anchor yakalayan
     * interceptor ve parçalı ClientHello yedeği. Parser kaynakları isteklerini
     * `AbstractContentParser` üzerinden `context.httpClient` ile kurduğu için
     * bu istemci onlara doğrudan geçer.
     */
    private val networkClient: OkHttpClient by lazy { buildNetworkClient() }

    /**
     * "Temiz" istemci: **DoH-oncelikli** DNS + parcali ClientHello + ayni TLS
     * yedegi. ISP DNS'i engelli sitede NXDOMAIN yerine sahte IP / engel sayfasi
     * dondurebiliyor; bu durumda TLS hatasi olusmadigi icin interceptor devreye
     * girmiyor ve liste "bos" gorunuyor (cihaz raporu 2026-11-23: 8 kaynakta
     * "Liste bos", ayni kaynaklar masaustunde 30/30 kart veriyor). Bu yuzden
     * bos sonuc/istisna alinan kaynakta ayni cagri temiz istemciyle bir kez
     * tekrarlanir ve kaynak o andan sonra temiz istemciye sabitlenir.
     */
    private val cleanClient: OkHttpClient by lazy { buildNetworkClient(preferDoh = true) }

    private val context by lazy { PulsarVideoLoaderContext(networkClient, cookieJar) }
    private val parser: ContentParser by lazy { context.newParserInstance(parserSource) }

    private val cleanContext by lazy { PulsarVideoLoaderContext(cleanClient, cookieJar) }
    private val cleanParser: ContentParser by lazy { cleanContext.newParserInstance(parserSource) }

    /** Ilk deneme engel sayfasina dustuyse kaynak temiz istemciye gecer. */
    @Volatile
    private var useClean = false

    /**
     * Bölüm eşlemesi: `getEpisodeList` sırasında parser'ın döndürdüğü özgün
     * [ContentChapter] nesneleri, üretilen `SChapter.url` anahtarıyla saklanır.
     * `getPages` bu nesnelerin `id`/`url` alanlarına ihtiyaç duyar; SChapter'dan
     * yeniden üretilen kopya parser'a yetmiyor. LRU, 2000 kayıt.
     */
    private val chapterCache = object : LinkedHashMap<String, ContentChapter>(256, 0.75f, true) {
        override fun removeEldestEntry(
            eldest: MutableMap.MutableEntry<String, ContentChapter>?,
        ): Boolean = size > MAX_CHAPTER_CACHE
    }

    /**
     * Kapak zenginleştirme önbelleği: içerik url'si -> kapak ("" = kapak yok).
     * Aynı içerik için `getDetails` tekrar sorulmaz; 1000 kayıtta sıfırlanır.
     */
    private val coverCache = ConcurrentHashMap<String, String>()

    /** Host'un kendi indirmeleri (kapak/video) için de aynı katman. */
    override val client: OkHttpClient
        get() = networkClient

    override val name: String = parserSource.title +
        if (parserSource.contentType == ContentType.HENTAI_VIDEO) " [18+]" else ""
    override val baseUrl: String by lazy { "https://" + parser.domain }
    override val supportsLatest: Boolean = true

    // ---- Liste -------------------------------------------------------------

    private fun pageStep(): Int = (activeParser() as? PagedContentParser)?.pageSize ?: 30

    private fun activeParser(): ContentParser = if (useClean) cleanParser else parser

    /**
     * Parser çağrısını yürütür; sonuç boşsa ya da istisna atarsa aynı çağrı
     * DoH-öncelikli istemciyle bir kez tekrarlanır. Tekrar başarılı olursa
     * kaynak temiz istemciye sabitlenir (`useClean`), böylece sonraki adımlar
     * da engel sayfasına düşmez.
     */
    private suspend fun <T> parserCall(
        empty: (T) -> Boolean,
        block: suspend (ContentParser) -> T,
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

    private suspend fun list(page: Int, order: SortOrder, query: String? = null): AnimesPage {
        val filter = if (query.isNullOrBlank()) {
            ContentListFilter.EMPTY
        } else {
            ContentListFilter(query = query)
        }
        // PagedContentParser offset'i kendi pageSize'iyle sayfaya çevirir;
        // offset daima pageSize'ın katı olmalı, yoksa sayfa atlanır.
        val offset = (page - 1) * pageStep()
        val entries = parserCall(empty = { it.isEmpty() }) { p -> p.getList(offset, order, filter) }
        // url/title boş kayıtlar hostta ValidationException üretir; atlanır.
        val pairs = entries.mapNotNull { content ->
            content.toSAnimeOrNull()?.let { content to it }
        }
        enrichMissingCovers(pairs)
        return AnimesPage(pairs.map { it.second }, entries.isNotEmpty())
    }

    /**
     * Liste kapakları AES ile şifreli gelir; parser çözemezse (ağ/AES hatası)
     * `coverUrl` null kalır. Kapaksız oranı %50'yi geçerse en fazla 10 öğe için
     * `getDetails` ile kapak tamamlanır. Paralel, 8 sn sınırlı; hata sessizce
     * atlanır ve sonuç url bazında önbelleklenir.
     */
    private suspend fun enrichMissingCovers(pairs: List<Pair<Content, SAnime>>) {
        if (pairs.isEmpty()) return
        val missing = pairs.filter { it.second.thumbnail_url.isNullOrBlank() }
        // Yarıdan fazlası kapaksız değilse ek istek yapılmaz.
        if (missing.size * 2 <= pairs.size) return
        val targets = missing.take(MAX_COVER_ENRICH)
        val resolved = withTimeoutOrNull(COVER_ENRICH_TIMEOUT_MS) {
            coroutineScope {
                targets.map { (content, _) ->
                    async(Dispatchers.IO) {
                        val cached = coverCache[content.url]
                        val cover = if (cached != null) {
                            cached.ifEmpty { null }
                        } else {
                            val details = runCatching {
                                parserCall(empty = { false }) { p -> p.getDetails(content) }
                            }.getOrNull()
                            val value = details?.let { coverUrlOf(it) }?.takeIf { it.isNotBlank() }
                            if (coverCache.size >= MAX_COVER_CACHE) coverCache.clear()
                            coverCache[content.url] = value.orEmpty()
                            value
                        }
                        content.url to cover
                    }
                }.awaitAll()
            }
        }
        if (resolved == null) return
        val byUrl = pairs.associateBy { it.first.url }
        resolved.forEach { (url, cover) ->
            if (!cover.isNullOrBlank()) {
                byUrl[url]?.second?.thumbnail_url = cover
            }
        }
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
    ): AnimesPage {
        if (query.isBlank()) return AnimesPage(emptyList(), false)
        // Aramayi desteklemeyen parser istisna atar; bos sonuca cevrilir.
        val direct = runCatching { list(page, SortOrder.RELEVANCE, query) }.getOrNull()
        if (direct != null && direct.animes.isNotEmpty()) return direct
        // Parser aramayi desteklemiyorsa ya da sorguyu yok sayip bos donduruyorsa:
        // populer listeyi cekip baslikta yerel filtre uygula. Kototoro'nun kaynak
        // testi aramayi zorunlu adim sayiyor; bu yedek olmadan kaynak "Arama:
        // sonuc yok" ile tumden dusuyordu (cihaz raporu 2026-11-23).
        val popular = runCatching { list(page, SortOrder.POPULARITY) }.getOrNull()
            ?: return AnimesPage(emptyList(), false)
        val needle = query.trim().lowercase()
        val matches = popular.animes.filter { it.title.lowercase().contains(needle) }
        // Yerel filtre tek sayfalik: hasNextPage=false, yoksa uygulama ayni
        // populer sayfayi tekrar tekrar ister.
        return AnimesPage(matches, false)
    }

    // ---- Detay / bölümler --------------------------------------------------

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getAnimeDetails(anime: SAnime): SAnime {
        val lib = anime.toLib()
        // Parser boş url/title döndürürse girişteki değerlere düşülür.
        return parserCall(empty = { false }) { p -> p.getDetails(lib) }
            .toSAnime(
                fallbackTitle = anime.title.ifBlank { lib.title },
                fallbackUrl = anime.url.ifBlank { lib.publicUrl },
            )
    }

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getEpisodeList(anime: SAnime): List<SEpisode> {
        val chapters = parserCall(empty = { it.isEmpty() }) { p ->
            p.getDetails(anime.toLib()).chapters ?: emptyList()
        }
        // Kronolojik artan -> Mihon'un beklediği en-yeni-önce sırası.
        return chapters
            .sortedBy { it.number }
            .asReversed()
            .mapNotNull { chapter ->
                // url'i boş bölüm hostta ValidationException üretir.
                if (chapter.url.isBlank()) return@mapNotNull null
                val episode = chapter.toSEpisode()
                synchronized(chapterCache) { chapterCache[episode.url] = chapter }
                episode
            }
    }

    // ---- Video -------------------------------------------------------------

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getHosterList(episode: SEpisode): List<Hoster> {
        val knownChapter = synchronized(chapterCache) { chapterCache[episode.url] }
        val pages = runCatching {
            parserCall(empty = { it.isEmpty() }) { p ->
                p.getPages(knownChapter ?: episode.toLibChapter())
            }
        }.getOrElse { return emptyList() }
        // Bazi parser'larda sayfa bir "sunucu" yer tutucusudur (or. HentaiPlay:
        // preview="Server 0", url=""); gercek akis adresi getPageUrl ile cozulur.
        val active = activeParser()
        val videos = pages.mapNotNull { page ->
            val raw = if (page.url.startsWith("http")) {
                page.url
            } else {
                runCatching {
                    withTimeoutOrNull(PAGE_URL_TIMEOUT_MS) { active.getPageUrl(page) }.orEmpty()
                }.getOrDefault("")
            }
            val url = raw.takeIf { it.startsWith("http") } ?: return@mapNotNull null
            val label = page.preview?.takeIf { it.isNotBlank() } ?: hostOf(url)
            val kind = if (isDirectStream(url)) "stream" else "embed"
            Video(url, "$label · $kind", headers = playbackHeaders)
        }.sortedBy { if (isDirectStream(it.videoUrl)) 0 else 1 }
        if (videos.isEmpty()) return emptyList()
        return listOf(Hoster(hosterUrl = episode.url, hosterName = name, videoList = videos))
    }

    /**
     * Oynatma isteklerine eklenecek basliklar. Kanit (2026-11-23): Erome akisi
     * referersiz 403, `Referer: https://www.erome.com/` ile 206 video/mp4;
     * FPO.XXX refererli 302→200.
     */
    private val playbackHeaders: okhttp3.Headers by lazy {
        okhttp3.Headers.Builder()
            .set("User-Agent", PLAYBACK_UA)
            .set("Referer", "$baseUrl/")
            .build()
    }

    override fun headersBuilder() = super.headersBuilder()
        .set("User-Agent", PLAYBACK_UA)
        .set("Referer", "$baseUrl/")

    @Suppress("OVERRIDE_DEPRECATION")
    override suspend fun getVideoList(hoster: Hoster): List<Video> = hoster.videoList.orEmpty()

    // Host'un SEpisode tabanlı varsayılan yolu videoListParse(Response) tek
    // başına bölüm bağlamı taşımaz. Liste burada, bölümü bilen yolda üretilir.
    // NOT: derleme ABI'si (extensions-lib 59418e2) bu iki üyeyi tanımıyor;
    // `override` yazılamaz. JVM imzaları host ABI'sindeki açık/soyut üyelerle
    // birebir aynı olduğundan çalışma anında sanal dağıtım bu metotlara düşer.
    @Suppress("OVERRIDE_DEPRECATION")
    suspend fun getVideoList(episode: SEpisode): List<Video> =
        getHosterList(episode).flatMap { it.videoList.orEmpty() }

    // AnimeHttpSource v16 host ABI'sinde soyut olan tek argümanlı üye
    // (AbstractMethodError kaynağı). Bölüm bilinmediği için yanıt gövdesindeki
    // doğrudan akışlar çıkarılır; bulunamazsa boş liste döner.
    fun videoListParse(response: Response): List<Video> {
        val body = runCatching { response.body?.string().orEmpty() }.getOrDefault("")
        return Regex("""https?://[^"'\s]+\.(?:m3u8|mp4)[^"'\s]*""")
            .findAll(body)
            .map { Video(it.value, "auto") }
            .take(20)
            .toList()
    }

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

    // ---- Ağ katmanı: DPI/DNS engeli (PulsarVideoSource ile aynı) -----------

    /**
     * Host istemcisini temel alır; üstüne DoH yedeği, TLS reset/trust-anchor
     * yakalayan interceptor ve parçalı ClientHello yedeği koyar. Parser'lar
     * isteklerini `context.httpClient` üzerinden kurduğu için bu istemci
     * onlara geçer; kaynak içinde ayrı istemci kurulmaz.
     */
    private fun buildNetworkClient(preferDoh: Boolean = false): OkHttpClient {
        val base = super.client.newBuilder()
            .cookieJar(cookieJar)
            .followRedirects(true)
            .followSslRedirects(true)
            .dns(PulsarVideoSource.DohFallbackDns(DEFAULT_DOH_ENDPOINT, preferDoh))
            .build()
        val trust = defaultTrustManager() ?: return base
        // Yedek istemci DoH-oncelikli: ISP DNS'i sahte IP dondurunce ilk deneme
        // TLS'te duser; yedekte gercek adres + parcali ClientHello kullanilir.
        val fragmenting = base.newBuilder()
            .dns(PulsarVideoSource.DohFallbackDns(DEFAULT_DOH_ENDPOINT, preferDoh = true))
            .sslSocketFactory(TlsFragmentingSocketFactory(), trust)
            .build()
        return base.newBuilder()
            .addInterceptor(PulsarVideoSource.TlsRetryInterceptor(fragmenting))
            .build()
    }

    private fun defaultTrustManager(): javax.net.ssl.X509TrustManager? = runCatching {
        val f = javax.net.ssl.TrustManagerFactory
            .getInstance(javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm())
        f.init(null as java.security.KeyStore?)
        f.trustManagers.filterIsInstance<javax.net.ssl.X509TrustManager>().firstOrNull()
    }.getOrNull()

    private companion object {
        /** PulsarVideoSource'daki varsayılan yedek uçla aynı. */
        const val DEFAULT_DOH_ENDPOINT = "https://cloudflare-dns.com/dns-query"

        /** Özgün ContentChapter eşlemesinin üst sınırı (LRU). */
        const val MAX_CHAPTER_CACHE = 2000

        /** Kapak zenginleştirmede en fazla kaç öğe için getDetails çağrılır. */
        const val MAX_COVER_ENRICH = 10

        /** Kapak önbelleğinin üst sınırı; aşılırsa sıfırlanır. */
        const val MAX_COVER_CACHE = 1000

        /** Kapak zenginleştirmesinin toplam süre sınırı. */
        const val COVER_ENRICH_TIMEOUT_MS = 8_000L

        /** Oynatma/istek başlıklarında kullanılan masaüstü UA. */
        const val PLAYBACK_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

        /** Yer tutucu sayfa için `getPageUrl` çağrısının üst sınırı. */
        const val PAGE_URL_TIMEOUT_MS = 15_000L
    }

    private fun isDirectStream(url: String): Boolean {
        val path = url.substringBefore('?').lowercase()
        return path.endsWith(".m3u8") || path.endsWith(".mp4") || url.contains(".m3u8?")
    }

    private fun hostOf(url: String): String = runCatching {
        java.net.URI(url).host.orEmpty().removePrefix("www.")
    }.getOrNull().orEmpty().ifBlank { "video" }

    // ---- Dönüşümler --------------------------------------------------------

    private fun Content.toSAnime(
        fallbackTitle: String = "",
        fallbackUrl: String = "",
    ): SAnime = SAnime.create().apply {
        // publicUrl = içeriğin GERÇEK sayfa adresi (Kotatsu sözleşmesi). `url` çoğu
        // parser'da yalnız kimliktir ("/NSFS-530"), detay isteği onunla 404 verir
        // (MemoJav 2026-11-23: /NSFS-530 -> 301 -> /NSFS-530 404). Önce publicUrl.
        url = this@toSAnime.publicUrl.ifBlank { this@toSAnime.url }.ifBlank { fallbackUrl }
        title = this@toSAnime.title.ifBlank { fallbackTitle }
        thumbnail_url = coverUrlOf(this@toSAnime)
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

    /** Liste için: zorunlu alanı boş kalan kayıt hostta patlamasın, atlansın. */
    private fun Content.toSAnimeOrNull(): SAnime? =
        toSAnime(fallbackTitle = title, fallbackUrl = url)
            .takeIf { it.url.isNotBlank() && it.title.isNotBlank() }

    /**
     * Parser'ın verdiği kapak göreliyse mutlaklaştırır; ikisi de boşsa null.
     * `file:`/`content:`/`data:` adresleri parser tarafından üretilmiş yerel
     * kaynaklardır (ör. Cg51 AES çözümü geçici dosya döndürür); mutlaklaştırma
     * bunları bozar, olduğu gibi bırakılır.
     */
    private fun coverUrlOf(content: Content): String? {
        val raw = content.largeCoverUrl?.takeIf { it.isNotBlank() }
            ?: content.coverUrl?.takeIf { it.isNotBlank() }
            ?: return null
        val lower = raw.lowercase()
        return when {
            lower.startsWith("http://") || lower.startsWith("https://") -> raw
            lower.startsWith("file:") || lower.startsWith("content:") ||
                lower.startsWith("data:") -> raw
            else -> raw.toAbsoluteUrl(parser.domain)
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
private class PulsarVideoLoaderContext(
    override val httpClient: OkHttpClient,
    override val cookieJar: CookieJar,
) : ContentLoaderContext() {

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
