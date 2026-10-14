package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("GHOSTOON", "ghostoon", "tr")
internal class Ghostoon(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.GHOSTOON, "ghostoon.com", 18) {
	override val datePattern = "d MMMM yyyy"
}
