package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("MINDAFANSUB", "mindafansub", "tr")
internal class Mindafansub(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.MINDAFANSUB, "mindafansub.dev", 18) {
	override val datePattern = "d MMMM yyyy"
}
