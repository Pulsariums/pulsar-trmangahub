package org.koitharu.kotatsu.parsers.site.madara.tr

import org.koitharu.kotatsu.parsers.MangaLoaderContext
import org.koitharu.kotatsu.parsers.MangaSourceParser
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import org.koitharu.kotatsu.parsers.site.madara.MadaraParser

@MangaSourceParser("GRIMELEK", "Grimelek", "tr")
internal class Grimelek(context: MangaLoaderContext) :
	MadaraParser(context, MangaParserSource.GRIMELEK, "siyahmelek.my")
