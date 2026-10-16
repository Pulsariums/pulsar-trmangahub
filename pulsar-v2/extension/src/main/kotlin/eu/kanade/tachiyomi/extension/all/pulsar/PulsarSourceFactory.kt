package eu.kanade.tachiyomi.extension.all.pulsar

import android.app.Application
import eu.kanade.tachiyomi.source.Source
import eu.kanade.tachiyomi.source.SourceFactory
import org.json.JSONObject
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.get
import java.io.InputStreamReader

/**
 * Pulsar-V2 Çok Dilli & Modüler Kaynak Fabrikası.
 *
 * BuildConfig parametrelerine göre dinamik olarak filtrelenmiş kaynakları yükler:
 * - PULSAR_LANG: Hedef dil kodu ("tr", "all", "en", "ja" vb.)
 * - PULSAR_NSFW: Yetişkin içerik bayrağı (true / false)
 */
class PulsarSourceFactory : SourceFactory {

    override fun createSources(): List<Source> {
        val targetLang = BuildConfig.PULSAR_LANG
        val wantAdult = BuildConfig.PULSAR_NSFW

        return runCatching {
            val app: Application = Injekt.get()
            val assetStream = app.assets.open("catalogue.json")
            val jsonText = InputStreamReader(assetStream, Charsets.UTF_8).use { it.readText() }
            val root = JSONObject(jsonText)
            val sourcesArray = root.optJSONArray("sources") ?: return@runCatching emptyList()

            val list = mutableListOf<Source>()
            for (i in 0 until sourcesArray.length()) {
                val item = sourcesArray.optJSONObject(i) ?: continue

                // 1. Dil Filtresi
                val itemLang = item.optString("lang", "all").lowercase()
                if (targetLang != "all" && itemLang != targetLang) {
                    continue
                }

                // 2. NSFW Filtresi
                val isNsfw = item.optInt("nsfw", 0) == 1
                if (isNsfw != wantAdult) {
                    continue
                }

                // 3. Güvenli Örnekleme (Tek bir bozuk tanım tüm eklentiyi çökertemez)
                runCatching {
                    list.add(PulsarSource(item, itemLang))
                }
            }
            list
        }.getOrDefault(emptyList())
    }
}
