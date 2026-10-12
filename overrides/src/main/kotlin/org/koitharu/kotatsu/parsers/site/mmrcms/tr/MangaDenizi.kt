package org.koitharu.kotatsu.parsers.site.mmrcms.tr

import okhttp3.Headers
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Interceptor
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.bitmap.Bitmap
import org.koitharu.kotatsu.parsers.bitmap.Rect
import org.koitharu.kotatsu.parsers.config.ConfigKey
import org.koitharu.kotatsu.parsers.core.PagedMangaParser
import org.koitharu.kotatsu.parsers.exception.ParseException
import org.koitharu.kotatsu.parsers.model.*
import org.koitharu.kotatsu.parsers.util.*
import org.koitharu.kotatsu.parsers.util.json.getStringOrNull
import org.koitharu.kotatsu.parsers.util.json.mapJSONNotNull
import java.time.OffsetDateTime
import java.util.EnumSet

/**
 * Pulsar override: the site dropped its MMRCMS HTML pages and now serves a JSON API under
 * `/api/v1/web`, with chapter images cut into a shuffled grid ("tiled-v1"). The grid size and
 * seed come with every page, so they travel in the url fragment (never sent to the server) and
 * [intercept] puts the tiles back. Ported from the keiyoushi MangaDenizi extension.
 */
@MangaSourceParser("MANGA_DENIZI", "MangaDenizi", "tr")
internal class MangaDenizi(context: MangaLoaderContext) :
	PagedMangaParser(context, MangaParserSource.MANGA_DENIZI, pageSize = 20) {

	override val configKeyDomain = ConfigKey.Domain("mangadenizi.net")

	override fun onCreateConfig(keys: MutableCollection<ConfigKey<*>>) {
		super.onCreateConfig(keys)
		keys.add(userAgentKey)
	}

	override val availableSortOrders: Set<SortOrder> = EnumSet.of(
		SortOrder.UPDATED,
		SortOrder.POPULARITY,
		SortOrder.RATING,
		SortOrder.ALPHABETICAL,
		SortOrder.NEWEST,
	)

	override val filterCapabilities: MangaListFilterCapabilities
		get() = MangaListFilterCapabilities(
			isSearchSupported = true,
			isSearchWithFiltersSupported = true,
			isMultipleTagsSupported = true,
		)

	override suspend fun getFilterOptions() = MangaListFilterOptions(
		availableTags = CATEGORIES.mapTo(LinkedHashSet()) { (title, key) ->
			MangaTag(key = key, title = title, source = source)
		},
		availableStates = EnumSet.of(
			MangaState.ONGOING,
			MangaState.FINISHED,
			MangaState.PAUSED,
			MangaState.ABANDONED,
		),
	)

	private val apiUrl get() = "https://$domain/api/v1"

	private fun apiHeaders(): Headers = getRequestHeaders().newBuilder()
		.set("Accept", "application/json")
		.set("Referer", "https://$domain/manga")
		.build()

	// ============================== List ==============================

	override suspend fun getListPage(page: Int, order: SortOrder, filter: MangaListFilter): List<Manga> {
		val url = "$apiUrl/web/manga".toHttpUrl().newBuilder().apply {
			addQueryParameter("page", page.toString())
			filter.query?.trim()?.nullIfEmpty()?.let { addQueryParameter("q", it) }
			addQueryParameter(
				"sort",
				when (order) {
					SortOrder.POPULARITY -> "popular"
					SortOrder.RATING -> "rating"
					SortOrder.ALPHABETICAL -> "name"
					SortOrder.NEWEST -> "year"
					else -> "latest"
				},
			)
			filter.states.forEach { state -> stateToApi(state)?.let { addQueryParameter("status[]", it) } }
			filter.tags.forEach { addQueryParameter("categories[]", it.key) }
		}.build()

		val items = webClient.httpGet(url, apiHeaders()).parseJson()
			.optJSONObject("data")?.optJSONObject("manga")?.optJSONArray("data")
			?: return emptyList()
		return items.mapJSONNotNull { toManga(it) }
	}

	private fun toManga(item: JSONObject): Manga? {
		val slug = item.getStringOrNull("slug") ?: return null
		val title = item.getStringOrNull("title") ?: return null
		return Manga(
			id = generateUid(slug),
			url = "/manga/$slug",
			publicUrl = "https://$domain/manga/$slug",
			title = title,
			altTitles = emptySet(),
			coverUrl = (item.getStringOrNull("cover_thumb_url") ?: item.getStringOrNull("cover_url"))
				?.toAbsoluteUrl(domain),
			largeCoverUrl = item.getStringOrNull("cover_url")?.toAbsoluteUrl(domain),
			authors = item.optJSONArray("authors").toNames(),
			description = item.getStringOrNull("description"),
			tags = buildSet {
				addAll(item.optJSONArray("categories").toTags())
				addAll(item.optJSONArray("genres").toTags())
			},
			state = parseState(item.getStringOrNull("status")),
			rating = RATING_UNKNOWN,
			contentRating = null,
			source = source,
		)
	}

	// ============================= Details =============================

	override suspend fun getDetails(manga: Manga): Manga {
		val slug = manga.url.trim('/').substringAfterLast('/')
		val details = webClient.httpGet("$apiUrl/web/manga/$slug", apiHeaders()).parseJson()
			.optJSONObject("data")?.optJSONObject("manga")
			?: throw ParseException("No manga data in response", manga.url)
		val parsed = toManga(details) ?: manga
		val chapters = details.optJSONArray("chapters").parseChapters(slug)
		return manga.copy(
			title = parsed.title,
			coverUrl = parsed.coverUrl ?: manga.coverUrl,
			largeCoverUrl = parsed.largeCoverUrl,
			authors = parsed.authors,
			description = parsed.description,
			tags = parsed.tags,
			state = parsed.state,
			chapters = chapters,
		)
	}

	private fun JSONArray?.parseChapters(mangaSlug: String): List<MangaChapter> {
		if (this == null) return emptyList()
		val list = mapJSONNotNull { item ->
			val slug = item.getStringOrNull("slug") ?: return@mapJSONNotNull null
			val number = item.opt("number")?.toString()?.takeIf { it != "null" && it.isNotBlank() } ?: "?"
			val title = item.getStringOrNull("title")
			MangaChapter(
				id = generateUid("$mangaSlug/$slug"),
				title = "Bölüm $number" + if (title.isNullOrBlank()) "" else ": $title",
				number = number.toFloatOrNull() ?: 0f,
				volume = 0,
				url = "/read/$mangaSlug/$slug",
				scanlator = null,
				uploadDate = parseDate(item.getStringOrNull("published_at")),
				branch = null,
				source = source,
			)
		}
		// The API order is not guaranteed; Kotatsu wants oldest first.
		return list.sortedBy { it.number }
	}

	private fun parseDate(value: String?): Long {
		if (value.isNullOrBlank()) return 0L
		return runCatching { OffsetDateTime.parse(value).toInstant().toEpochMilli() }.getOrDefault(0L)
	}

	// ============================== Pages ==============================

	override suspend fun getPages(chapter: MangaChapter): List<MangaPage> {
		val trimmed = chapter.url.trim('/').removePrefix("read/").removePrefix("manga/")
		val mangaSlug = trimmed.substringBefore('/')
		val chapterSlug = trimmed.substringAfter('/', "")
		if (mangaSlug.isEmpty() || chapterSlug.isEmpty()) {
			throw ParseException("Unexpected chapter url: ${chapter.url}", chapter.url)
		}
		val pages = webClient.httpGet("$apiUrl/reader/$mangaSlug/$chapterSlug", apiHeaders()).parseJson()
			.optJSONArray("pages") ?: return emptyList()
		return (0 until pages.length()).mapNotNull { index ->
			val page = pages.optJSONObject(index) ?: return@mapNotNull null
			val imageUrl = page.getStringOrNull("image_url")?.toAbsoluteUrl(domain) ?: return@mapNotNull null
			val scramble = page.optJSONObject("scramble")
			val url = if (
				scramble != null &&
				scramble.optString("method") == "tiled-v1" &&
				scramble.has("grid") && scramble.has("seed")
			) {
				"$imageUrl#$FRAGMENT_KEY${scramble.optInt("grid")};${scramble.optLong("seed")}"
			} else {
				imageUrl
			}
			MangaPage(id = generateUid(imageUrl), url = url, preview = null, source = source)
		}
	}

	// ========================= Image descrambling =========================

	override fun intercept(chain: Interceptor.Chain): Response {
		val request = chain.request()
		val fragment = request.url.fragment
		val response = chain.proceed(request)
		if (fragment == null || !fragment.startsWith(FRAGMENT_KEY) || !response.isSuccessful) {
			return response
		}
		val parts = fragment.removePrefix(FRAGMENT_KEY).split(';')
		val grid = parts.getOrNull(0)?.toIntOrNull() ?: return response
		val seed = parts.getOrNull(1)?.toLongOrNull() ?: return response
		return context.redrawImageResponse(response) { bitmap -> descramble(bitmap, grid, seed) }
	}

	private fun descramble(src: Bitmap, grid: Int, seed: Long): Bitmap {
		val w = src.width
		val h = src.height
		val l = maxOf(1, minOf(grid, minOf(w, h)))

		val u = createSlices(w, l)
		val c = createSlices(h, l)
		val m = shuffle(l, (ft(seed) xor ft(BO)).takeIf { it != 0L } ?: TA)
		val f = shuffle(l, (ft(seed) xor ft(VO)).takeIf { it != 0L } ?: TA)
		val p = mapSlices(u, m)
		val g = mapSlices(c, f)

		val dst = context.createBitmap(w, h)
		for (hIdx in 0 until l) {
			val v = c[f[hIdx]]
			val y = g[hIdx]
			for (bIdx in 0 until l) {
				val k = u[m[bIdx]]
				val t = p[bIdx]
				dst.drawBitmap(
					src,
					Rect(t.offset, y.offset, t.offset + t.length, y.offset + y.length),
					Rect(k.offset, v.offset, k.offset + k.length, v.offset + v.length),
				)
			}
		}
		return dst
	}

	private class Slice(val offset: Int, val length: Int)

	private fun createSlices(total: Int, pieces: Int): List<Slice> {
		val t = maxOf(1, total)
		val r = maxOf(1, minOf(pieces, t))
		return (0 until r).map { i ->
			val o = (i * t) / r
			val a = ((i + 1) * t) / r
			Slice(o, maxOf(1, a - o))
		}
	}

	private fun mapSlices(slices: List<Slice>, indices: IntArray): List<Slice> {
		var t = 0
		return indices.map { r ->
			val n = if (r in slices.indices) slices[r].length else 1
			val slice = Slice(t, n)
			t += n
			slice
		}
	}

	private fun shuffle(length: Int, seed: Long): IntArray {
		val t = IntArray(maxOf(1, length)) { it }
		var e = ft(seed).takeIf { it != 0L } ?: TA
		for (n in t.size - 1 downTo 1) {
			e = ft(e xor ft(e shl 13))
			e = ft(e xor (e ushr 17))
			e = ft(e xor ft(e shl 5))
			val i = (e % (n + 1)).toInt()
			val temp = t[n]
			t[n] = t[i]
			t[i] = temp
		}
		return t
	}

	private fun ft(value: Long): Long = value and 0xFFFFFFFFL

	// ============================= Utilities =============================

	private fun JSONArray?.toTags(): Set<MangaTag> {
		if (this == null) return emptySet()
		return mapJSONNotNull { item ->
			val name = item.getStringOrNull("name") ?: return@mapJSONNotNull null
			MangaTag(key = item.getStringOrNull("slug") ?: name, title = name, source = source)
		}.toSet()
	}

	private fun JSONArray?.toNames(): Set<String> {
		if (this == null) return emptySet()
		return mapJSONNotNull { it.getStringOrNull("name") }.toSet()
	}

	private fun parseState(value: String?): MangaState? = when (value?.lowercase()) {
		"ongoing" -> MangaState.ONGOING
		"completed" -> MangaState.FINISHED
		"hiatus" -> MangaState.PAUSED
		"cancelled" -> MangaState.ABANDONED
		else -> null
	}

	private fun stateToApi(state: MangaState): String? = when (state) {
		MangaState.ONGOING -> "ongoing"
		MangaState.FINISHED -> "completed"
		MangaState.PAUSED -> "hiatus"
		MangaState.ABANDONED -> "cancelled"
		else -> null
	}

	private companion object {
		const val FRAGMENT_KEY = "scr="
		const val TA = 2463534242L
		const val VO = 2654435769L
		const val BO = 2246822507L

		val CATEGORIES = listOf(
			"Aksiyon" to "aksiyon",
			"Bilim Kurgu" to "bilim-kurgu",
			"Doğaüstü" to "dogaustu",
			"Dövüş Sanatları" to "dovus-sanatlari",
			"Dram" to "dram",
			"Ecchi" to "ecchi",
			"Fantastik" to "fantastik",
			"Gerilim" to "gerilim",
			"Gizem" to "gizem",
			"Hayattan Bir Parça" to "hayattan-bir-parca",
			"Hayattan Kesitler" to "hayattan-kesitler",
			"Komedi" to "komedi",
			"Korku" to "korku",
			"Macera" to "macera",
			"Psikolojik" to "psikolojik",
			"Romantizm" to "romantizm",
			"Spor" to "spor",
			"Tarihi" to "tarihi",
			"Trajedi" to "trajedi",
		)
	}
}
