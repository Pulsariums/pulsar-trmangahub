package org.koitharu.kotatsu.parsers.site.nyxscans.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.config.ConfigKey
import org.koitharu.kotatsu.parsers.core.PagedMangaParser
import org.koitharu.kotatsu.parsers.exception.ParseException
import org.koitharu.kotatsu.parsers.model.*
import org.koitharu.kotatsu.parsers.util.*
import java.util.EnumSet

@MangaSourceParser("NYXSCANS_TR", "Nyx Scans", "tr")
internal class Nyxscans(context: MangaLoaderContext) :
	PagedMangaParser(context, MangaParserSource.NYXSCANS_TR, pageSize = 24) {

	override val configKeyDomain = ConfigKey.Domain("nyxscans.com")

	override val availableSortOrders: Set<SortOrder> = EnumSet.of(SortOrder.UPDATED)

	// TODO(recon): arama URL'si ve parametresi recon'da yok; isSearchSupported yalnızca istek gereği.
	override val filterCapabilities: MangaListFilterCapabilities =
		MangaListFilterCapabilities(isSearchSupported = true)

	// TODO(recon): tür/durum filtre listesi recon'da yok; boş bırakıldı.
	override suspend fun getFilterOptions() = MangaListFilterOptions(
		availableTags = emptySet(),
		availableStates = emptySet(),
	)

	// ============================== List ==============================

	override suspend fun getListPage(page: Int, order: SortOrder, filter: MangaListFilter): List<Manga> {
		// TODO(recon): sayfalama parametresi recon'da yok; yalnızca ilk sayfa (/series) parse ediliyor.
		if (page > 1 || !filter.query.isNullOrEmpty()) return emptyList()
		val doc = webClient.httpGet("https://$domain/series").parseHtml()
		return doc.select("div[class*='grid-cols-'] > div").mapNotNull { card ->
			val link = card.selectFirst("a[href^='/series/']") ?: return@mapNotNull null
			val url = link.attrAsRelativeUrl("href")
			val img = card.selectFirst("img")
			val title = img?.attr("alt")?.takeIf { it.isNotBlank() } ?: link.attr("title")
			if (title.isBlank()) return@mapNotNull null
			Manga(
				id = generateUid(url),
				url = url,
				publicUrl = url.toAbsoluteUrl(domain),
				title = title,
				altTitles = emptySet(),
				coverUrl = img?.attr("src")?.takeIf { it.isNotBlank() }?.toAbsoluteUrl(domain),
				largeCoverUrl = null,
				authors = emptySet(),
				description = null,
				tags = emptySet(),
				state = null,
				rating = card.selectFirst(".numscore")?.text()?.toFloatOrNull()?.div(10f) ?: RATING_UNKNOWN,
				contentRating = null,
				source = source,
			)
		}
	}

	// ============================= Details =============================

	override suspend fun getDetails(manga: Manga): Manga {
		val doc = webClient.httpGet(manga.url.toAbsoluteUrl(domain)).parseHtml()
		val root = doc.selectFirst(".series-hero-content") ?: doc
		val title = root.selectFirst("h1")?.text()?.takeIf { it.isNotBlank() } ?: manga.title
		val kicker = root.selectFirst(".series-kicker")?.text().orEmpty()
		val cover = root.selectFirst("img.series-cover")?.attr("src")?.takeIf { it.isNotBlank() }
			?.toAbsoluteUrl(domain)
		val banner = doc.selectFirst("img.series-banner")?.attr("src")?.takeIf { it.isNotBlank() }
			?.toAbsoluteUrl(domain)
		val tags = root.select(".series-genres > *").mapNotNullTo(LinkedHashSet()) { el ->
			val name = el.text().trim()
			if (name.isEmpty()) null else MangaTag(key = name.lowercase(), title = name, source = source)
		}
		val chapters = doc.select("a.chapter-card").toList().mapChapters(reversed = true) { i, el ->
			val href = el.attrAsRelativeUrl("href")
			val text = el.text()
			val number = NUMBER_REGEX.find(text)?.value?.toFloatOrNull() ?: (i + 1).toFloat()
			MangaChapter(
				id = generateUid(href),
				title = text.takeIf { it.isNotBlank() } ?: "Bölüm $number",
				number = number,
				volume = 0,
				url = href,
				scanlator = null,
				// TODO(recon): bölüm yayın tarihi selektörü yok.
				uploadDate = 0L,
				branch = null,
				source = source,
			)
		}
		return manga.copy(
			title = title,
			altTitles = root.selectFirst(".series-alt")?.text()
				?.takeIf { it.isNotBlank() }?.let { setOf(it) } ?: manga.altTitles,
			coverUrl = cover ?: manga.coverUrl,
			largeCoverUrl = banner ?: cover,
			// TODO(recon): yazar/çizer alanı etiket eşlemesi recon'da yok.
			authors = emptySet(),
			description = root.selectFirst(".series-description")?.text()?.takeIf { it.isNotBlank() },
			tags = tags,
			state = parseState(kicker.substringBefore('·').trim()),
			chapters = chapters,
		)
	}

	// ============================== Pages ==============================

	override suspend fun getPages(chapter: MangaChapter): List<MangaPage> {
		// TODO(recon): okuyucu sayfası HTML'i ve resim seçicisi recon'da yok.
		throw ParseException("Reader selectors not verified (TODO(recon))", chapter.url)
	}

	// ============================= Helpers =============================

	// TODO(recon): durum metinleri recon'da görülmedi; İngilizce karşılıklar varsayıldı.
	private fun parseState(value: String): MangaState? = when (value.lowercase()) {
		"ongoing" -> MangaState.ONGOING
		"completed", "finished" -> MangaState.FINISHED
		"hiatus", "paused" -> MangaState.PAUSED
		"dropped", "cancelled" -> MangaState.ABANDONED
		else -> null
	}

	private companion object {
		val NUMBER_REGEX = Regex("""\d+(?:\.\d+)?""")
	}
}
