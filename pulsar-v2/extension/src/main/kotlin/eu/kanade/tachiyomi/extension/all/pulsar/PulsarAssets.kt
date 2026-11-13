package eu.kanade.tachiyomi.extension.all.pulsar

import android.app.Application
import android.content.Context
import java.io.InputStreamReader

/**
 * Eklentinin KENDİ asset'lerini okur.
 *
 * Neden ayrı sınıf: eklenti kodunda `Injekt.get<Application>()` KONAK
 * uygulamanın Application'ıdır. `app.assets.open("patches.json")` konak
 * uygulamanın asset'lerine bakar; bizim APK'mızdaki dosya orada yoktur ve
 * hata `runCatching` içinde sessizce yutulur. Bu yüzden ölü kaynak listesi,
 * katalog ve domain düzeltmeleri cihaza HİÇ ulaşmıyordu; TR paketi 103
 * filtresiz motor kaynağı gösteriyordu.
 *
 * Çözüm: kendi paket adımızdan (BuildConfig.APPLICATION_ID) bir Context alıp
 * onun AssetManager'ını kullanmak. Paket çağıran uygulamada kurulu olduğu
 * için `createPackageContext` yalnız kaynak (kod dışı) ister; çalışmazsa
 * konak asset'lerine düşülür ve hata çağırana bırakılır.
 */
object PulsarAssets {

    private fun ownContext(app: Application): Context? = runCatching {
        app.createPackageContext(BuildConfig.APPLICATION_ID, 0)
    }.getOrNull()

    fun read(app: Application, name: String): String {
        val ctx = ownContext(app)
        val stream = (ctx?.assets ?: app.assets).open(name)
        return stream.use { InputStreamReader(it, Charsets.UTF_8).readText() }
    }
}
