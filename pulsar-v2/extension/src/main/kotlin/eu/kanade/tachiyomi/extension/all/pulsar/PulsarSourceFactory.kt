package eu.kanade.tachiyomi.extension.all.pulsar

import android.app.Application
import eu.kanade.tachiyomi.source.Source
import eu.kanade.tachiyomi.source.SourceFactory
import org.json.JSONObject
import org.koitharu.kotatsu.parsers.model.ContentType
import org.koitharu.kotatsu.parsers.model.MangaParserSource
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.get
import java.io.InputStreamReader

/**
 * Pulsar-V2 çift motorlu kaynak fabrikası.
 *
 * Nyora'dan ÖRNEK ALINAN mimari, KOPYALANMIŞ veri değil:
 *
 *  1. KOTATSU MOTORU — APK'ya paketlenmiş kotatsu-parsers-redo enum'ları
 *     (Nyora'nın yüzlerce kaynağının geldiği yer). Dil + NSFW'e göre süzülür,
 *     DEAD_SOURCES ile elenir. Her kaynak LAZY: yalnızca açıldığında parser
 *     kurulur — Nyora'nın 900 kaynağı belleği şişirmeyen sırrı budur.
 *  2. DATA-DRIVEN KATALOG — kendi pipeline'ımızın ürettiği catalogue.json:
 *     kullanıcı-doğrulanmış TR siteleri, motorun tanımadığı özel alan adları,
 *     probe'da doğrulanmış domainler. (Motorla aynı hosta gelen kayıt olabilir;
 *     Keiyoushi eklentileriyle Nyora'nın yan yana çalışması gibi bu da zararsız,
 *     Nyora bilinçli olarak host-dedup YAPMAZ — eager parser kurulumu listeyi
 *     çökertir.)
 *
 * Her iki katman da PULSAR_LANG / PULSAR_NSFW flavor parametreleriyle süzülür;
 * tek bozuk kaynak tüm listeyi düşüremez (her kayıt runCatching — Mihon,
 * createSources patlarsa EKLENTİNİN TAMAMINI iptal eder).
 */
class PulsarSourceFactory : SourceFactory {

    override fun createSources(): List<Source> {
        val targetLang = BuildConfig.PULSAR_LANG
        val wantAdult = BuildConfig.PULSAR_NSFW

        val app: Application = runCatching { Injekt.get() }.getOrNull()
            ?: return emptyList()

        runCatching { PulsarPatches.load(app) }

        // 1) kotatsu-parsers motoru — Nyora'nın kanıtladığı enum yolu
        val engine: List<Source> = runCatching<List<Source>> {
            MangaParserSource.entries.mapNotNull { entry ->
                runCatching {
                    val name = entry.name
                    when {
                        name in PulsarPatches.DEAD_SOURCES -> null
                        (entry.contentType == ContentType.HENTAI) != wantAdult -> null
                        targetLang != "all" && entry.locale.isNotBlank() && entry.locale != targetLang -> null
                        else -> PulsarKotatsuSource(entry, entry.locale.ifBlank { "all" })
                    }
                }.getOrNull()
            }
        }.getOrDefault(emptyList())

        // 2) kendi data-driven kataloğumuz — motorun tanımadığı TR/özel siteler
        val catalogue: List<Source> = runCatching<List<Source>> {
            val jsonText = app.assets.open("catalogue.json").use {
                InputStreamReader(it, Charsets.UTF_8).readText()
            }
            val root = JSONObject(jsonText)
            val sourcesArray = root.optJSONArray("sources")

            val list = mutableListOf<Source>()
            if (sourcesArray != null) for (i in 0 until sourcesArray.length()) {
                val item = sourcesArray.optJSONObject(i) ?: continue
                val itemLang = item.optString("lang", "all").lowercase()
                if (targetLang != "all" && itemLang != targetLang) continue
                val isNsfw = item.optInt("nsfw", 0) == 1
                if (isNsfw != wantAdult) continue

                val domain = item.optString("domain", "").lowercase().removePrefix("www.")
                val alt = item.optJSONArray("altDomains").orEmptyStrings().map {
                    it.lowercase().removePrefix("www.")
                }
                if (PulsarPatches.isDeadHost(domain, alt)) continue   // probe ölü dedi

                runCatching { list.add(PulsarSource(item, itemLang)) }
            }
            list
        }.getOrDefault(emptyList())

        return engine + catalogue
    }

    private fun org.json.JSONArray?.orEmptyStrings(): List<String> {
        if (this == null) return emptyList()
        return (0 until length()).mapNotNull { optString(it).takeIf { v -> v.isNotBlank() } }
    }
}
