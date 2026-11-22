package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import eu.kanade.tachiyomi.animesource.AnimeSource
import eu.kanade.tachiyomi.animesource.AnimeSourceFactory
import org.json.JSONObject
import org.skepsun.kototoro.parsers.model.ContentParserSource

/**
 * Kaynak listesi APK'ya gömülü `VIDEO_CATALOGUE` JSON'undan okunur.
 * Manga tarafındaki `PulsarSourceFactory` deseninin video eşi.
 *
 * İki motor aynı APK'da yan yana:
 *  - `engine":"video"`  -> veri-güdümlü [PulsarVideoSource] (config seçicileri),
 *  - `engine":"parser"` -> kototoro-parsers kayıt defterinden
 *    [PulsarKotatsuVideoSource] (Nyora taktiği). Parser örneği lazy kurulur;
 *    bozuk (`isBroken`) ya da kütüphanede bulunmayan kayıt sessizce atlanır,
 *    tek bozuk kayıt tüm listeyi düşürmez.
 */
class PulsarVideoSourceFactory : AnimeSourceFactory {

    override fun createSources(): List<AnimeSource> {
        val root = JSONObject(VIDEO_CATALOGUE)
        val arr = root.optJSONArray("sources") ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val cfg = arr.optJSONObject(i) ?: return@mapNotNull null
            if (cfg.optString("engine") == "parser") {
                parserSource(cfg)
            } else {
                // config'i henüz ölçülmemiş kaynak arayüzde görünmesin.
                if (cfg.optJSONObject("config")?.length() == 0) return@mapNotNull null
                PulsarVideoSource(cfg, cfg.optString("lang", "en"))
            }
        }
    }

    private fun parserSource(cfg: JSONObject): AnimeSource? {
        val enumName = cfg.optString("parser", "").trim()
        if (enumName.isEmpty()) return null
        return runCatching {
            val source = ContentParserSource.valueOf(enumName)
            if (source.isBroken) {
                null
            } else {
                val lang = cfg.optString("lang", source.locale.ifBlank { "all" })
                PulsarKotatsuVideoSource(source, lang.ifBlank { "all" })
            }
        }.getOrNull()
    }
}
