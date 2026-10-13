package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("TOONHANE", "toonhane", "tr")
internal class Toonhane(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.TOONHANE, "toonhane.com", 18) {
	override val datePattern = "d MMMM yyyy"
}
