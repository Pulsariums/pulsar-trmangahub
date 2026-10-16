package eu.kanade.tachiyomi.extension.all.pulsar

import android.app.Application
import org.json.JSONObject
import uy.kohesive.injekt.Injekt
import uy.kohesive.injekt.api.get
import java.io.InputStreamReader

/**
 * Derleme hattımızın (06_prepare_assets.py) ürettiği asset tabanlı yama defteri.
 *
 * Nyora bu tabloyu SourcePatches.kt olarak hardcoded taşır; biz CI'daki
 * probe/onarm verimizden (03_probe_fast.py OTOMATIK_TAMIR_*) otomatik üretiyoruz.
 * Böylece alan adı taşınmaları ve ölü kaynak elemesi, kod derlenmeden
 * katalog verisinden APK'ya girer.
 *
 *  - DOMAIN_OVERRIDES: parser enum adı VEYA eski domain → canlı domain
 *  - DEAD_SOURCES:     DNS'i ölen / kumar-spam'a düşen enum adları (gizlenir)
 *  - DEAD_HOSTS:       katalog domain bazlı ölüler (engine domain eşleşmesiyle)
 *  - TITLE_OVERRIDES:  rebrand eden kaynakların güncel görünen adları
 */
object PulsarPatches {

    @Volatile
    private var loaded = false

    val DOMAIN_OVERRIDES: MutableMap<String, String> = mutableMapOf()
    val DEAD_SOURCES: MutableSet<String> = mutableSetOf()
    val DEAD_HOSTS: MutableSet<String> = mutableSetOf()
    val TITLE_OVERRIDES: MutableMap<String, String> = mutableMapOf()

    fun load(app: Application = Injekt.get()) {
        if (loaded) return
        synchronized(this) {
            if (loaded) return
            runCatching {
                val text = app.assets.open("patches.json").use {
                    InputStreamReader(it, Charsets.UTF_8).readText()
                }
                val root = JSONObject(text)
                root.optJSONObject("domainOverrides")?.let { o ->
                    o.keys().forEach { k -> DOMAIN_OVERRIDES[k] = o.getString(k) }
                }
                root.optJSONArray("deadSources")?.let { a ->
                    for (i in 0 until a.length()) DEAD_SOURCES.add(a.getString(i))
                }
                root.optJSONArray("deadHosts")?.let { a ->
                    for (i in 0 until a.length()) DEAD_HOSTS.add(a.getString(i).lowercase())
                }
                root.optJSONObject("titleOverrides")?.let { o ->
                    o.keys().forEach { k -> TITLE_OVERRIDES[k] = o.getString(k) }
                }
            }
            loaded = true
        }
    }

    /** Catalogue/kotlin tarafı: bu domain (veya alias'larından biri) ölü mü? */
    fun isDeadHost(domain: String, altDomains: List<String> = emptyList()): Boolean {
        val all = (listOf(domain) + altDomains).map { it.lowercase().removePrefix("www.") }
        return all.any { DEAD_HOSTS.contains(it) || DEAD_HOSTS.contains("www.$it") }
    }
}
