# HEDEF — Pulsar kaynak ağının tamamlanması

Bu dosya "iş bitti" tanımını ve çalışma döngüsünü sabitler. Her tur bu dosyaya göre yürür.

## 1. Bitiş tanımı (ölçülebilir)

İş, aşağıdaki **beş koşulun tamamı** sağlandığında biter:

1. **Belirsiz kayıt sıfır.** `source-status.json` içinde `pending` + `unknown` toplamı **0**. Her kayıt `active`, `failed` veya `dead` olur.
2. **Her `active` kayıt kanıtlı.** Kaydın `device` veya `health` alanında en az bir geçiş kanıtı var: `list`, `chapters`, `pages` üçü de `pass` (cihaz testi ya da yerel harness).
3. **Her `failed`/`dead` kayıt gerekçeli.** `reason` veya `device.detail` alanında tek cümlelik neden var: ölü/park, DNS yok, Cloudflare, JS render, imza/CSRF, coğrafi blok, üyelik kilidi.
4. **Test havuzu yalnız "yeniden test bekleyen" kaynak taşır.** `test` paketindeki her kayıt en son turda tamir edilmiş olmalı; test edilmiş ama tamir edilmemiş kaynak havuzda durmaz.
5. **Her test kayıtlı.** Her cihaz/harness koşusu `pulsar-v2/data/testler/` altına zaman damgalı girer ve `test-kayitlari.md` tablosunda görünür.

## 2. Bugünkü durum (2026-11-17)

| Katman | Toplam | active | failed | pending | unknown |
|---|---|---|---|---|---|
| Katalog (bizim) | 430 | 171 | 174 | 5 | 80 |
| Motor (JitPack parser) | 1272 | 122 | 927 | 202 | 21 |
| **Toplam** | **1702** | **293** | **1101** | **207** | **101** |

Yayın (embed): tr 40 · tr18 7 · global 221 · global18 25 · test 68.

**Kalan iş iki ayrı kovada:**
- **85 katalog kaydı** (80 unknown + 5 pending) → yerel harness ile test edilebilir.
- **223 motor kaynağı** (202 pending + 21 unknown) → yerel test imkânsız (ABI), yalnız cihaz testiyle kapanır.

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
