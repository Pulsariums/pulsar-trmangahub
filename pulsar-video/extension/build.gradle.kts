// Pulsar Video — Aniyomi eklentisi (Mihon manga paketinden bağımsız).
// Kototoro/Aniyomi bu APK'yı `tachiyomi.animeextension` feature'ı ile tanır.
plugins {
    id("com.android.application") version "8.7.3"
    id("org.jetbrains.kotlin.android") version "2.1.0"
}

android {
    namespace = "eu.kanade.tachiyomi.animeextension.all.pulsarvideo"
    compileSdk = 35

    defaultConfig {
        applicationId = "eu.kanade.tachiyomi.animeextension.all.pulsarvideo"
        minSdk = 23
        targetSdk = 35
        // Aniyomi/Kototoro: versionName "<extLib>.<patch>" kontratı.
        versionCode = (project.findProperty("pulsarVersionCode") as String? ?: "2").toInt()
        versionName = project.findProperty("pulsarVersionName") as String? ?: "1.0.2"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module", "META-INF/*.version")
    }
}

dependencies {
    // Aniyomi eklenti API'si (AnimeSource, AnimeHttpSource, Video, Hoster, SAnime, SEpisode).
    // Sürüm, Aniyomi eklentilerinin kullandığı v16 ABI'sine sabit (sb-extensions-source ile aynı).
    compileOnly("com.github.aniyomiorg:extensions-lib:59418e2c2aab286dc654dde31e071aa82cb0ff7c")
    // okhttp: Aniyomi lib compileOnly veriyor; derleme icin acikca eklenir (calisma aninda host saglar).
    compileOnly("com.squareup.okhttp3:okhttp:4.12.0")
    compileOnly("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    implementation("org.jsoup:jsoup:1.18.3")
    implementation("org.json:json:20240303")
}
