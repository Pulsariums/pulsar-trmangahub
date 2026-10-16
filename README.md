# 🌟 Pulsar Manga Hub (V2)

**Mihon / Tachiyomi için Nyora Mimarisiyle Güçlendirilmiş, Çok Dilli ve Birleşik Manga Eklenti Deposu**

Artık onlarca farklı APK kurup güncellemekle uğraşmanıza gerek yok! Pulsar-V2, tüm Türkçe ve küresel manga kaynaklarını **Nyora tekniğiyle tek bir eklenti paketi** içinde toplar, ölü siteleri otomatik eler, yeni adrese taşınanları otomatik onarır ve cihaz üzerinde (on-device) sıfır sunucu bağımlılığıyla çalışır.

---

## 🚀 Mihon'a Tek Tıkla Ekleme

Mihon veya Tachiyomi yüklü cihazınızdan aşağıdaki butona tıklayarak depoyu anında ekleyebilirsiniz:

[![Mihon'a Ekle](https://img.shields.io/badge/Mihon'a%20Ekle-Depo%20Bağlantısı-blue?style=for-the-badge&logo=android)](tachiyomi://add-repo?url=https%3A%2F%2Fraw.githubusercontent.com%2FPulsariums%2Fpulsar-trmangahub%2Fmain%2Fpulsar-v2%2Frepo%2Findex.min.json)

### 📋 Manuel Ekleme (Tek Link)

1. **Mihon / Tachiyomi** uygulamasını açın.
2. **Daha Fazla (More) → Ayarlar (Settings) → Gözat (Browse) → Eklenti depoları (Extension repos) → +** simgesine dokunun.
3. Aşağıdaki **tek bağlantıyı** yapıştırın:

```text
https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo/index.min.json
```

*(Alternatif GitHub Pages Aynası: `https://pulsariums.github.io/pulsar-trmangahub/index.min.json`)*

4. **Gözat → Eklentiler** sekmesine gidin ve ihtiyacınız olan paketi tek tıkla kurun.

---

## 📦 Dağıtılan Birleşik Paketler

| Eklenti Adı | Paket Kimliği | İçerik ve Kapsam | Kaynak Sayısı |
|---|---|---|---|
| **Pulsar TR** | `…pulsar.tr` | Tüm Türkçe Normal (SFW) Manga ve Webtoon Siteleri | **92 Kaynak** |
| **Pulsar TR 18+** | `…pulsar.tr18` | Tüm Türkçe Yetişkin (+18 / NSFW / Yaoi / Yuri) Siteleri | **17 Kaynak** |
| **Pulsar Global** | `…pulsar.global` | Dünya Genelindeki Normal Manga Siteleri | **92+ Kaynak** |
| **Pulsar Global 18+** | `…pulsar.global18` | Dünya Genelindeki Yetişkin Manga Siteleri | **17+ Kaynak** |

> **Not:** Tek bir eklenti (örn: *Pulsar TR*) yüklediğinizde, içindeki 92 kaynak Mihon'un kaynaklar listesinde ayrı ayrı görünür ve dilediğinizi kullanabilirsiniz.

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
