package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("RUYAMANGA2", "ruyamanga2", "tr")
internal class Ruyamanga2(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.RUYAMANGA2, "ruyamanga2.com", 18) {
	override val datePattern = "d MMMM yyyy"
}
