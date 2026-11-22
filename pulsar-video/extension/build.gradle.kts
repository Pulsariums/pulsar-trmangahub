// Pulsar Video — Aniyomi eklentisi (Mihon manga paketinden bağımsız).
// Kototoro/Aniyomi bu APK'yı `tachiyomi.animeextension` feature'ı ile tanır.
plugins {
    id("com.android.application") version "8.7.3"
    // kototoro-parsers jar'ı Kotlin 2.2.10 ile derlenmiş: metadata'sını
    // okuyabilmek için derleyici aynı hatta olmalı.
    id("org.jetbrains.kotlin.android") version "2.2.10"
}

android {
    namespace = "eu.kanade.tachiyomi.animeextension.all.pulsarvideo"
    compileSdk = 35

    defaultConfig {
        applicationId = "eu.kanade.tachiyomi.animeextension.all.pulsarvideo"
        minSdk = 23
        targetSdk = 35
        // Aniyomi/Kototoro: versionName "<extLib>.<patch>" kontratı.
        versionCode = (project.findProperty("pulsarVersionCode") as String? ?: "3").toInt()
        versionName = project.findProperty("pulsarVersionName") as String? ?: "16.1"
        // `aniyomix.extensionLib` = Aniyomi eklenti ABI sürümü. Loader bunu
        // Float/Double olarak okur, string kabul etmez; sayı olarak verilir.
        manifestPlaceholders["pulsarExtLib"] = 16
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

    // Nyora taktiği (video): kototoro-parsers kayıt defterindeki onlarca video
    // parser'ı tek APK'ya gömülür. JitPack'te 1.7 jar'ı yok (pom 404); master
    // derlemesi (c12cf9d0e9, 2026-11-20) ContentParser API'sini taşıyor.
    // Host'un sağladığı kütüphaneler paketlenmesin: yalnız parser kodu girer.
    implementation("com.github.skepsun:kototoro-parsers:master-SNAPSHOT") {
        exclude(group = "com.squareup.okhttp3")
        exclude(group = "com.squareup.okio")
        exclude(group = "org.jetbrains.kotlinx")
        exclude(group = "org.jetbrains.kotlin")
        exclude(group = "androidx.collection")
        exclude(group = "org.json")
    }

    implementation("org.jsoup:jsoup:1.21.2")
    implementation("org.json:json:20240303")
}
