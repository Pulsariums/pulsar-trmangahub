plugins {
    id("com.android.application")
    kotlin("android")
    kotlin("plugin.serialization")
}

val pulsarLang: String = (project.findProperty("pulsarLang") as String?) ?: "tr"
val pulsarNsfw: Boolean = (project.findProperty("pulsarNsfw") as String?)?.let { it == "1" || it.equals("true", true) } ?: false
val pulsarPkgSuffix: String = (project.findProperty("pulsarPkgSuffix") as String?) ?: if (pulsarNsfw) ".tr18" else ".tr"
val pulsarName: String = (project.findProperty("pulsarName") as String?) ?: if (pulsarNsfw) "Pulsar TR 18+" else "Pulsar TR"

android {
    namespace = "eu.kanade.tachiyomi.extension.all.pulsar"
    compileSdk = 34

    defaultConfig {
        applicationId = "eu.kanade.tachiyomi.extension.all.pulsar$pulsarPkgSuffix"
        minSdk = 26
        targetSdk = 34
        versionCode = 106001
        versionName = "1.6.1"

        buildConfigField("String", "PULSAR_LANG", "\"$pulsarLang\"")
        buildConfigField("boolean", "PULSAR_NSFW", "$pulsarNsfw")
        buildConfigField("String", "PULSAR_NAME", "\"$pulsarName\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources {
            excludes += setOf(
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE*",
                "META-INF/NOTICE*",
                "META-INF/*.kotlin_module"
            )
        }
    }
}

dependencies {
    // Mihon runtime host provides these APIs
    compileOnly("androidx.annotation:annotation:1.7.1")
    compileOnly("com.squareup.okhttp3:okhttp:5.0.0-alpha.12")
    compileOnly("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.0")
    compileOnly("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    // Bundled parsers and utils
    implementation("org.jsoup:jsoup:1.17.2")
    implementation("org.json:json:20240303")
}
