package eu.kanade.tachiyomi.extension.tr.{{PKG}}

import eu.kanade.tachiyomi.multisrc.initmanga.InitManga
import keiyoushi.annotation.Source

@Source
abstract class {{CLASS}} : InitManga() {

    override val mangaUrlDirectory = "manga"

    override val latestUrlSlug = "recently-updated"

    override val popularUrlSlug = "manga-ranking"
}
