# HEDEF — Pulsar kaynak ağının tamamlanması

Bu dosya "iş bitti" tanımını ve çalışma döngüsünü sabitler. Her tur bu dosyaya göre yürür.

## 1. Bitiş tanımı (ölçülebilir)

İş, aşağıdaki **beş koşulun tamamı** sağlandığında biter:

1. **Unknown yalnız ölçülmemiş kayıt.** `unknown` yalnız gerçekten ölçülmemiş kayıtlar için kalır; her `pending` kayıt `test` paketinde ve cihaz testi bekliyor olarak işaretlidir. Gerekçe: CI ile cihaz ağı farklı.
2. **Her `active` kayıt kanıtlı.** Kaydın `device` veya `health` alanında en az bir geçiş kanıtı var: `list`, `chapters`, `pages` üçü de `pass` (cihaz testi ya da yerel harness).
3. **Her `failed`/`dead` kayıt gerekçeli.** `reason` veya `device.detail` alanında tek cümlelik neden var: ölü/park, DNS yok, Cloudflare, JS render, imza/CSRF, coğrafi blok, üyelik kilidi.
4. **Test havuzu yalnız "yeniden test bekleyen" kaynak taşır.** `test` paketindeki her kayıt en son turda tamir edilmiş olmalı; test edilmiş ama tamir edilmemiş kaynak havuzda durmaz.
5. **Her test kayıtlı.** Her cihaz/harness koşusu `pulsar-v2/data/testler/` altına zaman damgalı girer ve `test-kayitlari.md` tablosunda görünür.

## 2. Bugünkü durum (2026-11-17)

| Katman | Toplam | active | failed | pending | dead | unknown |
|---|---|---|---|---|---|---|
| Katalog (bizim) | 439 | 233 | 102 | 0 | 104 | 0 |
| Motor (JitPack parser) | 1272 | 123 | 404 | 218 | 527 | 0 |
| **Toplam** | **1711** | **356** | **506** | **218** | **631** | **0** |

Yayın (embed): tr 50 · tr18 8 · global 269 · global18 29 · test 218. Kaynak: commit `e79c88d` (kopya motor temizliği), build `44174345687`.

**Kalan iş tek kovada:**
- **218 motor kaynağı** yalnız cihaz testiyle kapanır (yerel test imkânsız: Mihon ABI). Katalog tarafında bekleyen kayıt **0**.

**Bu oturumda kapananlar (özet):**
- Katalog ölçüm kuyruğunun tamamı (199 dilim) ve 197 "geçici görünümlü" hata tarandı.
- Dalga 4-7 + canlılık dalgaları: 228 config düzeltmesi, 409 kayıt ölü işaretlendi.
- 197 geçici hata + 430 EN dışı + 139 EN motor kaynağı canlılık taraması: toplam **157 kaynak teste geri alındı**.
- 12 motor kaynağı kendi katalog kaydına çevrildi (qimanga, toonily, comichubfree, mangapark, manhwatoon, mangahub, mangahentai, mangaowl, comizy, kakamanga, toontop, spiderscans, hentaiango…), bunların 9'u harness ile doğrulanıp yayına alındı.
- 73 kopya motor kaydı kapatıldı (aynı domainde çalışan katalog kaydı varken).

**Bu oturumda düzeltilen motor kusurları:** boş bölüm listesinde istisna (`chapterListParse`), `pageApiIdPattern` içinde host, `www.` id uyuşmazlığı, `kapali` kaynakların paket listesine sızması, `dead`/`reason` alanlarının `pulsar status` koşusunda silinmesi, harness'ın listenin ilk serisine takılması.

## 3. Döngü

```
ölç  →  sınıflandır  →  tamir et  →  uygula  →  yeniden test  →  promote / failed
 ↑                                                                      │
 └──────────────────────── yeni build ──────────────────────────────────┘
```

Her adımın sahibi:

| Adım | Araç / ajan | Çıktı |
|---|---|---|
| Ölç | `kaynak-tamirci` (canlı `curl`), `tools/harness/run.sh` | `.work/tamir*/<domain>.json` |
| Sınıflandır | ana oturum | sınıf dosyaları (`.work/test*/<SINIF>.csv`) |
| Tamir et | `kaynak-tamirci` | config alanları + `kanit` |
| Uygula | `katalog-uygulayici` | `config` altına yazım, teste dönüş, build |
| Test | harness (katalog) / cihaz (motor) | geçti/düştü |
| Promote | `device.pass` + `health.ok` | `active`, kendi paketi |

## 4. Sınıflandırma sözlüğü

| Karar | Anlam | Son durum |
|---|---|---|
| `LISTE_DUZELT`, `CHAPTER_SECICI`, `CHAPTER_AJAX`, `READER_*`, `PAGE_API`, `PAGE_SCRIPT`, `ARAMA_*`, `ESKI_DOMAIN` | ayarla düzeltilebilir | `config` yazılır, teste döner |
| `JS_RENDER` | veri istemcide üretiliyor, uç bulunamadı | `failed` (API avı yapıldıktan sonra) |
| `CLOUDFLARE` | HTML ve API kapalı | `failed` |
| `OLU`, `PARK`, `DNS_YOK` | site yok | `dead` |
| `RATE_LIMIT`, `SERBEST` (üyelik/geo) | erişim kısıtlı | `failed` |
| `HARNESS_SINIRI` | site sağlam, ölçüm aracı yetmiyor | `test`te kalır, cihaz testi bekler |

## 5. Motor kaynakları için kural

Motor kaynağı yerelde test edilemiyor (Mihon ABI). Bu yüzden:
- `pending`/`unknown` motor kaynakları **cihaz testi** ile kapanır.
- Cihaz testi için test paketine alınmaları gerekir; bu, `state=pending` ile olur.
- 927 `failed` motor kaynağı için iki yol var: (a) cihazda yeniden test, (b) aynı siteyi okuyan **kendi katalog kaydını** yazıp motoru devre dışı bırakmak (OkuToon deseni).

## 6. Bu turun iş listesi

1. 85 katalog belirsizini harness ile test et → `active`/`failed` ayrımı.
2. Kalan tamir kuyruğundan (994 "tamir edilebilir") sıradaki 40-60 katalog kaydını ajanlara dağıt.
3. `status.rs`: cihaz/harness `pass` verdiyse manuel `sorun` etiketini yok say (bayat etiket sınıfı).
4. Motor `pending` 202 kaynağı cihaz testine hazırla (test paketine al, tek build).
5. Sonuçları zaman damgalı kayda işle.
