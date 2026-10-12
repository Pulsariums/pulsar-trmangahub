package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("{{ID}}", "{{TITLE}}", "tr")
internal class {{CLASS}}(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.{{ID}}, "{{DOMAIN}}", 18) {
	override val datePattern = "d MMMM yyyy"
}
