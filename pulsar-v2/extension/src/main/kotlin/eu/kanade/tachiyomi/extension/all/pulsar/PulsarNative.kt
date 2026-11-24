package eu.kanade.tachiyomi.extension.all.pulsar

import eu.kanade.tachiyomi.extension.all.pulsar.native.HipmhSource
import eu.kanade.tachiyomi.extension.all.pulsar.native.WebmotaSource
import eu.kanade.tachiyomi.source.Source
import org.json.JSONObject

/**
 * `engine: "native"` kaynak kaydı.
 *
 * Config motoru bir sitenin istemci-taraflı akışını (JS ile üretilen sayfa
 * listesi, imzalı API, özel başlık) ifade edemiyorsa o site için elle yazılmış
 * sınıf burada seçilir. Sınıflar [PulsarSource]'u miras alır: `id`, `name`,
 * `baseUrl`, `headers` ve yayın filtresi (`PulsarData.allowed`) değişmeden
 * çalışır; yalnız istek/ayrıştırma metotları değişir.
 *
 * Kayıt anahtarı katalogdaki `native` alanıdır; boşsa `id` kullanılır.
 * İlk kullanım: Mihon Copy20 hasadı (2026-11-24).
 */
internal object PulsarNative {

    fun create(item: JSONObject, lang: String): Source? {
        val key = item.optString("native", "").trim().ifBlank { item.optString("id", "").trim() }
        return when (key) {
            // Hasat edilen Mihon kaynakları (Copy20, 2026-11-24)
            "webmota" -> WebmotaSource(item, lang)
            "hipmh" -> HipmhSource(item, lang)
            else -> null
        }
    }
}
