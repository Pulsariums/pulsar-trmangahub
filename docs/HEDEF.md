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
| Katalog (bizim) | 429 | 156 | 63 | 108 | 102 | 0 |
| Motor (JitPack parser) | 1272 | 126 | 905 | 53 | 188 | 0 |
| **Toplam** | **1701** | **282** | **968** | **161** | **290** | **0** |

Yayın (embed): tr 38 · tr18 5 · global 214 · global18 25 · test 161. Kaynak: commit `819fe73` (dalga 6), build `44148308861`.

**Kalan iş iki ayrı kovada:**
- **108 katalog kaydı** → yerel harness ile test edilebilir (`tools/harness/run.sh`, koşu: `.work/harness-2026-11-17-p161.log`).
- **53 motor kaynağı** → yerel test imkânsız (ABI), yalnız cihaz testiyle kapanır.

**Bu oturumda kapananlar:** katalog ölçüm kuyruğunun tamamı (199 dilim) ölçüldü; dalga 4-5-6'da toplam 197 kayıt ölçülmüş seçicilerle düzeltildi, 23 kayıt ölü işaretlendi. Düzeltilen her kayıt test havuzuna döndü; `pending` sayısının 161'e çıkması bunun sonucudur, gerileme değil.

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
