# 🌟 Pulsar Manga Hub

**Hem Mihon / Tachiyomi (APK) hem de Kototoro (JAR) için Bağımsız, Çok Dilli Manga Depoları**

Bu depo üç ayrı dağıtım hattı sunar (manga için ikisi, video için biri):
1. **Kototoro için Klasik JAR Deposu:** Kototoro uygulamasının yerel uzantı sistemiyle %100 uyumlu, 4 modüler `.jar` paketi (`tr`, `tr_nsfw`, `global`, `global_nsfw`).
2. **Mihon için Yeni Birleşik APK Deposu (Pulsar-V2):** Nyora tekniğiyle tek APK altında toplanmış, sıfır sunucu bağımlılıklı otomatik tamirli eklenti deposu.

---

## ☕ 1. Kototoro (JAR) Deposu Kurulumu

Kototoro uygulamasında doğrudan çalışan klasik JAR paketleridir:

1. Kototoro uygulamasında **Ayarlar → Eklentiler / Paketler** bölümüne gidin.
2. Depo URL'si olarak şunu ekleyin:
   ```text
   https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/jar/index.min.json
   ```
   *(veya doğrudan klasör yolu: `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/jar`)*
3. İstediğiniz paketi (`tr`, `tr_nsfw`, `global`, `global_nsfw`) seçip indirin.

---

## 🚀 2. Mihon / Tachiyomi (APK) Deposu Kurulumu

Mihon yüklü cihazınızdan tek tıkla eklemek için:

[![Mihon'a Ekle](https://img.shields.io/badge/Mihon'a%20Ekle-Depo%20Bağlantısı-blue?style=for-the-badge&logo=android)](tachiyomi://add-repo?url=https%3A%2F%2Fraw.githubusercontent.com%2FPulsariums%2Fpulsar-trmangahub%2Fmain%2Findex.min.json)

### 📋 Manuel Ekleme (Tek Link)

1. **Mihon / Tachiyomi** uygulamasını açın.
2. **Daha Fazla (More) → Ayarlar (Settings) → Gözat (Browse) → Eklenti depoları (Extension repos) → +** simgesine dokunun.
3. Aşağıdaki depo adresini yapıştırın:
   ```text
   https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo/index.min.json
   ```
   *(kök ayna adres: `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/index.min.json`)*
4. **Gözat → Eklentiler** sekmesinden dilediğiniz paketi kurun.

---

## 🎬 3. Video (Anime) Kaynakları — Kototoro / Aniyomi

Manga paketlerinden bağımsız, **Aniyomi formatında** ayrı bir eklenti: **Pulsar Video** (normal) ve **Pulsar Video 18+**. Kototoro ve Aniyomi'de çalışır.

Depo adresi:
```text
https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-video/repo
```

Kototoro → Ayarlar → Kaynaklar → Depo ekle → adresi yapıştır. Ayrıntılar, kaynak durumları ve CloudStream / JAR birleşik deposu: [pulsar-video/README.md](pulsar-video/README.md)

| Paket | İçerik | Kaynak |
|---|---|---|
| **Pulsar Video** | GogoAnime, AniWorld ve diğer normal video siteleri | **9** |
| **Pulsar Video 18+** | Yetişkin video siteleri | **18** |

---

## 📦 Paket Dağıtımları ve Kapsam

### Kototoro (JAR) Paketleri
| Paket | Dosya | Kapsam |
|---|---|---|
| **Pulsar TR** | `jar/apk/tr.jar` | Türkçe normal manga/webtoon kaynakları |
| **Pulsar TR (NSFW)** | `jar/apk/tr-nsfw.jar` | Türkçe yetişkin / +18 kaynaklar |
| **Pulsar Global** | `jar/apk/global.jar` | Dünya çapında normal kaynaklar (İngilizce, Japonca vb.) |
| **Pulsar Global (NSFW)** | `jar/apk/global-nsfw.jar` | Dünya çapında yetişkin kaynaklar |

### Mihon (APK) Birleşik Paketleri
| Eklenti Adı | Paket Kimliği | İçerik ve Kapsam | Kaynak Sayısı | Sürüm |
|---|---|---|---|---|
| **Pulsar TR** | `…pulsar.tr` | Tüm Türkçe Normal Manga ve Webtoon Siteleri | **41** | **v1.6.165** |
| **Pulsar TR 18+** | `…pulsar.tr18` | Tüm Türkçe Yetişkin (+18 / NSFW) Siteleri | **7** | **v1.6.165** |
| **Pulsar Global** | `…pulsar.global` | Dünya Genelindeki Normal Manga Siteleri | **217** | **v1.6.165** |
| **Pulsar Global 18+** | `…pulsar.global18` | Dünya Genelindeki Yetişkin Siteleri | **25** | **v1.6.165** |
| **Pulsar Test** | `…pulsar.test` | Deneysel / doğrulanmamış kaynaklar | **2** | **v1.6.165** |

> **Not:** Tek bir eklenti (örn: *Pulsar TR*) yüklediğinizde, içindeki 41 kaynak Mihon'un kaynaklar listesinde ayrı ayrı görünür ve dilediğinizi kullanabilirsiniz.

> **18+ içerik:** Yetişkin kaynaklar yalnızca `tr18` ve `global18` paketlerinde yer alır. `test` paketi ise deneysel kaynaklar içindir; kararlı kullanım için önerilmez.

---

## ⚡ Yeni Sistemin Avantajları ve Özellikleri

* **Tek Seferde Kurulum:** 60-70 tane ayrı APK indirme, izin verme ve güncelleme karmaşası tamamen bitti.
* **Akıllı Veri Birleştirmesi (Smart Deduplication):** Farklı kaynaklarda aynı siteye işaret eden birden fazla kayıt (örn. eski `.net` ve yeni `.com`) tek bir zengin kaynakta birleştirilir.
* **Otomatik Alan Adı Tamiratı:**
  * Site yeni bir adrese yönlenmişse (HTTP 301/302), sistem yeni adresi tespit edip otomatik günceller.
  * Ana domain kapandığında yedek (alternatif) domain canlıysa sistem kaynağı otomatik olarak o adrese taşır.
* **Kumar / Spam Botu Koruması:** Kapanan manga sitelerinin alan adları bahis siteleri tarafından ele geçirildiğinde sistem bunu anında tespit eder ve pakete sokmaz.
* **Hafif ve Hızlı (Lazy Loading):** Yüzlerce kaynak aynı anda belleği şişirmez; sadece tıkladığınız kaynak anlık başlatılır.
* **Mihon Cloudflare Entegrasyonu:** Cloudflare korumalı siteler Mihon'un dahili "WebView ile Aç" özelliğiyle tamamen uyumludur.
* **Geleceğe Hazır Çok Dilli Mimari:** Gelecekte Japonca, İngilizce, Korece gibi yeni diller tek bir parametre (`--lang ja`) ile anında bağımsız paketlere dönüştürülebilir.

---

## 🔗 Bağlantılar

* **Pano:** <https://pulsariums.github.io/pulsar-trmangahub/>
* **Kaynak Tablosu:** <https://pulsariums.github.io/pulsar-trmangahub/kaynaklar.html>
* **Depo Adresi:** `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo/index.min.json`

---

## 📊 Raporlar ve Veriler

* [Canlı Kaynak Kataloğu (JSON)](pulsar-v2/data/catalogue.json)
* [Detaylı Hata Teşhis ve Otomatik Tamirat Raporu](pulsar-v2/DIAGNOSTICS_REPORT.md)
* [Mihon Repo İndeksi (JSON)](pulsar-v2/repo/index.min.json)

---

## 🛠️ Mimari ve Klasör Yapısı

```text
pulsar-v2/
├── data/
│   ├── raw_sources.json          # 4.900+ ham kaynak havuzu
│   ├── deduplicated.json         # Tekilleştirilmiş ve marka bazında birleştirilmiş kaynaklar
│   ├── liveness.json             # 180+ kaynağın derinlemesine HTTP/DNS teşhis verileri
│   └── catalogue.json            # 109 çalışan ve tamir edilmiş nihai kaynak kataloğu
├── scripts/
│   ├── 01_aggregate.py           # 5 farklı kaynaktan veri toplayıcı
│   ├── 02_dedupe.py              # Akıllı domain ve marka birleştirici
│   ├── 03_probe_fast.py          # Otomatik tamirat ve paralel canlılık testi motoru
│   ├── 04_auto_generator.py      # Otomatik seçici ve katalog derleyici
│   └── 05_build_repo.py          # Mihon depo ve indeks üretici
└── extension/                    # Nyora tarzı SourceFactory + HttpSource Android köprüsü
    ├── src/main/kotlin/.../
    │   ├── PulsarSourceFactory.kt
    │   ├── PulsarSource.kt
    │   └── EngineRegistry.kt
    └── build.gradle.kts
```

---
*Lisans: MIT / Apache 2.0 - Pulsar Manga Hub Ekibi tarafından geliştirilmiştir.*
