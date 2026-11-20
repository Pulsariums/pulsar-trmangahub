package eu.kanade.tachiyomi.animeextension.all.pulsarvideo

import eu.kanade.tachiyomi.animesource.AnimeSource
import eu.kanade.tachiyomi.animesource.AnimeSourceFactory
import org.json.JSONObject

/**
 * Kaynak listesi APK'ya gömülü `VIDEO_CATALOGUE` JSON'undan okunur.
 * Manga tarafındaki `PulsarSourceFactory` deseninin video eşi.
 */
class PulsarVideoSourceFactory : AnimeSourceFactory {

    override fun createSources(): List<AnimeSource> {
        val root = JSONObject(VIDEO_CATALOGUE)
        val arr = root.optJSONArray("sources") ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val cfg = arr.optJSONObject(i) ?: return@mapNotNull null
            // config'i henüz ölçülmemiş kaynak arayüzde görünmesin.
            if (cfg.optJSONObject("config")?.length() == 0) return@mapNotNull null
            PulsarVideoSource(cfg, cfg.optString("lang", "en"))
        }
    }
}
