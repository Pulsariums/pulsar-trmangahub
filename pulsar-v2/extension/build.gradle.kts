// Pulsar-V2 birleşik Mihon eklentisi.
//
// Nyora porter örüntüsü (kopya DEĞİL, örnek): bu modül, geçici bir resmi Mihon
// checkout'una `:pulsar-extension` olarak bağlanıp orada derlenir. Mihon'un
// `mihonx` eklenti-derleme pluginleri ve `:source-api` / `:core:common` API'leri
// build sırasında oradan gelir; APK yalnız eklentidir, uygulama asla derlenmez.
//
// Flavor kimliği CI'dan -P ile geçer (pulsar_build.sh):
//   -PpulsarPkgSuffix=.tr / .tr18 / .global / .global18 / .en ...
//   -PpulsarName="Pulsar TR"
//   -PpulsarLang=tr|all|en   -PpulsarNsfw=0|1
plugins {
    alias(mihonx.plugins.android.application)
}

fun prop(name: String, default: String) = (project.findProperty(name) as String?) ?: default

val pulsarPkgSuffix = prop("pulsarPkgSuffix", ".global")
val pulsarName = prop("pulsarName", "Pulsar")
val pulsarLang = prop("pulsarLang", "all")
val pulsarNsfw = prop("pulsarNsfw", "0")
// kotatsu-parsers-redo revresi (JitPack). pulsar_build.sh bunu her derlemede geçebilir.
val parsersRef = prop("parsersRef", "59c033ecfd")

android {
    namespace = "eu.kanade.tachiyomi.extension.all.pulsar"

    defaultConfig {
        applicationId = "eu.kanade.tachiyomi.extension.all.pulsar$pulsarPkgSuffix"
        versionCode = 1
        // KONTRAT (Nyora'dan örnek alınan Mihon davranışı): versionName TAM OLARAK
        // "<tachiyomix.extensionLib>.<patch>" biçiminde olmalı. Mihon repo libVersion'ı
        // versionName.substringBeforeLast('.') olarak türetir; manifest'teki
        // extensionLib'den (1.6) büyük olursa "kalıcı güncelleme rozeti" oluşur.
        // generate_repo.py bunu APK'nın kendi manifestine karşı doğrular ve patlar.
        // minSdk/targetSdk/compileSdk/desugaring: mihonx android-base plugini ayarlar.
        versionName = "1.6.1"

        buildConfigField("String", "PULSAR_LANG", "\"$pulsarLang\"")
        buildConfigField("boolean", "PULSAR_NSFW", (pulsarNsfw != "0").toString())
        buildConfigField("String", "PULSAR_NAME", "\"$pulsarName\"")
        manifestPlaceholders["pulsarName"] = pulsarName
    }

    signingConfigs {
        create("pulsar") {
            // Tek kararlı imza anahtarı: CI'da workflows/derleme adımında her seferinde
            // üretilir (SIGNING KEY FINGERPRINT = repo.json'daki değer; APK'lardan
            // otomatik okunur — elle eşleştirme YOK, Nyora generate-repo örüntüsü).
            // Depoya konan keystore Android'e APK kuramaz; Kototoro/Mihon yalnız
            // sertifika PARMAK İZİNİ karşılaştırır.
            storeFile = file(prop("pulsarKeystore", System.getProperty("user.home") + "/.android/debug.keystore"))
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("pulsar")
        }
    }
}

dependencies {
    // Hostta çalışana zamanda sağlanır (extension child-first classloader).
    compileOnly(projects.sourceApi)
    compileOnly(projects.core.common)
    compileOnly(libs.okhttp.core)
    compileOnly(libs.kotlinx.coroutines.core)

    // Cihaz üstü motor — Nyora'nın ~900 kaynağının geldiği kotatsu-parsers-redo.
    // TR dahil yüzlerce dil kaynağını derlenmiş enum olarak taşır; Pulsar'ın
    // data-driven katalogunu ÇOĞALTMAZ, TAMAMLAR.
    implementation("com.github.clquwu:kotatsu-parsers-redo:$parsersRef")
    implementation("org.jsoup:jsoup:1.17.2")
    implementation("org.json:json:20240303")
}

// Mihon host Kotlin stdlib/coroutines/okhttp'i kendisi sağlar; APK'ya ikinci kopyayı
// koymak classloader'da LinkageError üretir (Nyora porter kuralı — birebir uygulanır).
configurations.configureEach {
    if (name.endsWith("RuntimeClasspath")) {
        exclude(group = "org.jetbrains.kotlin")
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-core")
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-core-jvm")
        exclude(group = "com.squareup.okhttp3", module = "okhttp")
    }
}
