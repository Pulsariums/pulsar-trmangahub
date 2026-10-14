package org.koitharu.kotatsu.parsers.site.holyscans.tr

import org.jsoup.nodes.Element
import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.config.ConfigKey
import org.koitharu.kotatsu.parsers.core.PagedMangaParser
import org.koitharu.kotatsu.parsers.exception.ParseException
import org.koitharu.kotatsu.parsers.model.*
import org.koitharu.kotatsu.parsers.util.*
import java.net.URLEncoder
import java.util.EnumSet

@MangaSourceParser("HOLYSCANS", "HolyScans", "tr")
internal class Holyscans(context: MangaLoaderContext) :
	PagedMangaParser(context, MangaParserSource.HOLYSCANS, pageSize = 24) {

	override val configKeyDomain = ConfigKey.Domain("holyscans.com.tr")

	override val availableSortOrders: Set<SortOrder> = EnumSet.of(SortOrder.UPDATED)

	override val filterCapabilities: MangaListFilterCapabilities =
		MangaListFilterCapabilities(isSearchSupported = false)

	override suspend fun getFilterOptions() = MangaListFilterOptions(
		availableTags = emptySet(),
		availableStates = emptySet(),
	)

	// ============================== List ==============================

	override suspend fun getListPage(page: Int, order: SortOrder, filter: MangaListFilter): List<Manga> {
		val query = filter.query?.takeIf { it.isNotBlank() }
		if (query != null && !SEARCH_SUPPORTED) return emptyList()
		if (page > 1 && PAGE_PARAM == null) return emptyList()
		val params = buildList {
			if (page > 1 && PAGE_PARAM != null) add("$PAGE_PARAM=$page")
			if (query != null) add("search=" + URLEncoder.encode(query, "UTF-8"))
		}
		val separator = if (LIST_PATH.contains('?')) "&" else "?"
		val url = buildString {
			append("https://").append(domain).append(LIST_PATH)
			if (params.isNotEmpty()) append(separator).append(params.joinToString("&"))
		}
		val doc = webClient.httpGet(url).parseHtml()
		val items = doc.select(LIST_ITEM)
		if (items.isEmpty() && query == null && page == 1) {
			throw ParseException("List selector matched no items: check list.item", url)
		}
		return items.mapNotNull { item ->
			val link = item.value(SEL_LIST_LINK)?.toRelativeUrl(domain) ?: return@mapNotNull null
			val title = item.value(SEL_LIST_TITLE) ?: return@mapNotNull null
			Manga(
				id = generateUid(link),
				url = link,
				publicUrl = link.toAbsoluteUrl(domain),
				title = title,
				altTitles = emptySet(),
				coverUrl = item.value(SEL_LIST_COVER)?.toAbsoluteUrl(domain),
				largeCoverUrl = null,
				authors = emptySet(),
				description = null,
				tags = emptySet(),
				state = null,
				rating = RATING_UNKNOWN,
				contentRating = null,
				source = source,
			)
		}
	}

	// ============================= Details =============================

	override suspend fun getDetails(manga: Manga): Manga {
		val doc = webClient.httpGet(manga.url.toAbsoluteUrl(domain)).parseHtml()
		val title = doc.value(SEL_DETAIL_TITLE) ?: manga.title
		val cover = doc.value(SEL_DETAIL_COVER)?.toAbsoluteUrl(domain)
		val tags = doc.values(SEL_DETAIL_GENRES).mapNotNullTo(LinkedHashSet()) { name ->
			MangaTag(key = name.lowercase(), title = name, source = source)
		}
		val chapters = doc.select(CHAPTER_ITEM)
			.mapNotNull { el ->
				val href = el.value(SEL_CHAPTER_LINK)?.toRelativeUrl(domain) ?: return@mapNotNull null
				el to href
			}
			.mapChapters(reversed = true) { i, (el, href) ->
				val text = el.value(SEL_CHAPTER_TITLE) ?: el.text().trim()
				val number = NUMBER_REGEX.find(text)?.value?.toFloatOrNull() ?: (i + 1).toFloat()
				MangaChapter(
					id = generateUid(href),
					title = text.takeIf { it.isNotBlank() } ?: "Bölüm $number",
					number = number,
					volume = 0,
					url = href,
					scanlator = null,
					uploadDate = 0L,
					branch = null,
					source = source,
				)
			}
		return manga.copy(
			title = title,
			altTitles = manga.altTitles,
			coverUrl = cover ?: manga.coverUrl,
			largeCoverUrl = cover ?: manga.largeCoverUrl,
			authors = emptySet(),
			description = doc.value(SEL_DETAIL_DESCRIPTION),
			tags = tags,
			state = parseState(doc.value(SEL_DETAIL_STATUS).orEmpty()),
			chapters = chapters,
		)
	}

	// ============================== Pages ==============================

	override suspend fun getPages(chapter: MangaChapter): List<MangaPage> {
		val url = chapter.url.toAbsoluteUrl(domain)
		val doc = webClient.httpGet(url).parseHtml()
		val images = doc.select(READER_IMAGES).mapNotNull { img ->
			READER_ATTRS.firstNotNullOfOrNull { attr -> img.value(Sel(null, attr)) }
		}.map { it.toAbsoluteUrl(domain) }.distinct()
		if (images.isEmpty()) {
			throw ParseException("No reader images matched: check reader.images", url)
		}
		return images.map { imageUrl ->
			MangaPage(id = generateUid(imageUrl), url = imageUrl, preview = null, source = source)
		}
	}

	// ============================= Helpers =============================

	private fun parseState(value: String): MangaState? {
		val v = value.lowercase()
		return when {
			v.contains("ongoing") || v.contains("devam") || v.contains("yayın") -> MangaState.ONGOING
			v.contains("completed") || v.contains("finished") || v.contains("tamamlan") || v.contains("bitti") ->
				MangaState.FINISHED
			v.contains("hiatus") || v.contains("paused") || v.contains("askı") -> MangaState.PAUSED
			v.contains("dropped") || v.contains("cancelled") || v.contains("bırakıl") -> MangaState.ABANDONED
			else -> null
		}
	}

	private fun Element.value(sel: Sel?): String? {
		if (sel == null) return null
		val el: Element = when {
			sel.css == null -> this
			this.`is`(sel.css) -> this
			else -> selectFirst(sel.css) ?: return null
		}
		val v = if (sel.attr == null) el.text() else el.attr(sel.attr)
		return v.trim().takeIf { it.isNotEmpty() }
	}

	private fun Element.values(sel: Sel?): List<String> {
		if (sel == null) return emptyList()
		val els = if (sel.css == null) listOf(this) else select(sel.css)
		return els.mapNotNull { it.value(Sel(null, sel.attr)) }
	}

	private fun String.toRelativeUrl(domain: String): String = toAbsoluteUrl(domain).substringAfter("://$domain")

	private class Sel(val css: String?, val attr: String?)

	private companion object {
		const val LIST_PATH = "/"
		val PAGE_PARAM: String? = null
		val SEARCH_SUPPORTED: Boolean = false
		const val LIST_ITEM = "div.manga-card-v2.holy-private-card"
		const val CHAPTER_ITEM = "div.mc-chapters"
		const val READER_IMAGES = "div.chapter-content-area.holy-fit img"
		val READER_ATTRS = listOf("src", "data-src")

		val SEL_LIST_LINK: Sel? = Sel("a", "href")
		val SEL_LIST_TITLE: Sel? = Sel("img", "alt")
		val SEL_LIST_COVER: Sel? = Sel("img", "src")
		val SEL_DETAIL_TITLE: Sel? = Sel("h1.hs-title", null)
		val SEL_DETAIL_COVER: Sel? = Sel("meta[property=\"og:image\"]", "content")
		val SEL_DETAIL_DESCRIPTION: Sel? = Sel("#pane-summary", null)
		val SEL_DETAIL_GENRES: Sel? = Sel("div.hs-genres", null)
		val SEL_DETAIL_STATUS: Sel? = null
		val SEL_CHAPTER_LINK: Sel? = Sel("a", "href")
		val SEL_CHAPTER_TITLE: Sel? = Sel("a", null)

		val NUMBER_REGEX = Regex("""\d+(?:\.\d+)?""")
	}
}
