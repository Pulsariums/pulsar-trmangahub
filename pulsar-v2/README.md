# Pulsar Manga Hub V2 (Mihon / Tachiyomi Deposu)

Nyora mimarisinden esinlenilmiş, cihaz üzerinde (on-device) çalışan, **çok dilli ve modüler** birleşik Mihon eklenti deposu.

Eski sistemdeki gibi onlarca ayrı APK kurmanıza gerek yoktur. Tek bir paket kurarak o dildeki tüm çalışan kaynaklara aynı anda erişebilirsiniz.

---

## Mihon'a Nasıl Eklenir?

1. **Mihon / Tachiyomi** uygulamasını açın.
2. **Daha Fazla (More) → Ayarlar (Settings) → Gözat (Browse) → Eklenti depoları (Extension repos) → +** simgesine dokunun.
3. Aşağıdaki depo URL'sini yapıştırın:

```text
https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-v2/repo/index.min.json
```

4. Ardından **Gözat → Eklentiler** sekmesine gelin. Yalnızca ihtiyacınız olan paketi kurun:

| Eklenti Adı | Paket | İçerik | Kaynak Sayısı |
|---|---|---|---|
| **Pulsar TR** | `…pulsar.tr` | Tüm Türkçe Normal (SFW) Manga Siteleri | **92 Kaynak** |
| **Pulsar TR 18+** | `…pulsar.tr18` | Tüm Türkçe Yetişkin (+18 / NSFW) Siteleri | **17 Kaynak** |
| **Pulsar Global** | `…pulsar.global` | Tüm Dillerdeki Normal Manga Siteleri | **92 Kaynak** |
| **Pulsar Global 18+** | `…pulsar.global18` | Tüm Dillerdeki Yetişkin Manga Siteleri | **17 Kaynak** |

---

## Mimari Özellikler

- **Tek Tıkla Kurulum:** Her site için ayrı APK indirme ve güncelleme derdi bitti.
- **Düşük Bellek Kullanımı (Lazy Loading):** Yüzlerce kaynak aynı anda belleğe yüklenmez; yalnızca tıkladığınız kaynak anlık başlatılır.
- **Cloudflare Desteği:** Mihon'un dahili "WebView ile Aç" özelliğiyle tamamen uyumludur.
- **Otomatik Bölüm Normalizasyonu:** Sitelerin ters/düz bölüm sıralama karmaşasını kronolojik olarak otomatik çözer.
- **Çok Dilli Modülerlik:** Gelecekte `--lang ja`, `--lang en` parametreleriyle istenen her dil tek komutla üretilebilir.
