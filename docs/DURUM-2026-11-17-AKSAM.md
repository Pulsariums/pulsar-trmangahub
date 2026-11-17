# DURUM — 2026-11-17 akşam

Kaynaklar: `pulsar-v2/repo/index.min.json`, `pulsar-v2/data/source-status.json`, `pulsar-v2/data/test-kayitlari.md`, `pulsar-v2/depo/tamir-kuyrugu.json`, `docs/HEDEF.md`, `git log`.

## 1. Yayın

Sürüm **v1.6.161** (index'ten).

| Paket | Kaynak |
|---|---|
| Pulsar TR | 32 |
| Pulsar TR 18+ | 6 |
| Pulsar Global | 216 |
| Pulsar Global 18+ | 25 |
| Pulsar Test | 37 |
| **Toplam** | **316** |

## 2. Durum defteri

`source-status.json` toplam **1702** kayıt (`catalogue` 430 · `engine` 1272).

| Durum | Toplam | Katalog | Motor |
|---|---|---|---|
| active | 288 | 163 | 125 |
| failed | 1357 | 212 | 1145 |
| dead | 0 | 0 | 0 |
| pending | 0 | 0 | 0 |
| unknown | 57 | 55 | 2 |

`dead` ve `pending` dosyada hiç anahtar olarak geçmiyor; sayaç bu yüzden 0.

## 3. Hedef durumu (`docs/HEDEF.md` beş koşulu)

| # | Koşul | Durum | Kanıt |
|---|---|---|---|
| 1 | pending + unknown = 0 | **Hayır** | `DURUM {"active":288,"failed":1357,"unknown":57}` |
| 2 | Her active kanıtlı (list/chapters/pages pass) | **Kısmen** | 288/288 active `device.status=pass`, ayrıntı "yerel harness L…/C…/P…"; ama `device_step` tek adım adı tutuyor, üç alan ayrı ayrı dolu değil |
| 3 | Her failed/dead gerekçeli | **Hayır** | 1331/1357 kayıtta `reason`/`device.detail`/`health.detail` var; 26 kayıt gerekçesiz (ör. Mangadotnet, AsuraComic, MangaReader.site, Manganato, lekmanga.net) |
| 4 | Test havuzu yalnız yeniden test bekleyeni taşır | **Hayır** | `test` paketinde 37 kayıt, hepsi `state=unknown`; sınıflandırılmamış kayıt havuzda |
| 5 | Her test kayıtlı | **Kısmen** | `test-kayitlari.md` tablosunda 5 satır; `data/testler/` altında 4 zaman damgalı dosya; "harness-belirsiz" satırının dosyası yok |

## 4. Bugün uygulanan partiler

`git log --since=2026-11-17 -- pulsar-v2/data/catalogue.json` → **17 commit**:

- `3115490` feat(motor): link[as=fetch] sayfa destegi; 7 parti tek pakette uygulandi
- `4102b9f` fix(katalog): sleptmanga sorun etiketi kaldirildi, tr paketine gecti
- `9d23131` feat(motor): kaynak basina basliklar ve POST sayfa API; test grubu partileri uygulandi
- `def6648` fix(durum): test grubu raporu islendi (19 gecti, 55 dustu); 4 mutlak listPath
- `b035393` fix(katalog): okuyucu/detay/liste partileri uygulandi; thzq= dizisi okunuyor
- `fa8c5cd` fix(katalog): 21 kapak secicisi + 6 arama ucu uygulandi; rozet filtresi dosya adina indirildi
- `6e73028` fix(katalog): seriye sabitlenmis chapterAjaxUrl sablonu; okutoon JSON API geri
- `83a2bdd` fix(katalog): OkuToon secicileri Keiyoushi OkuToon.kt'ye gore
- `614c27c` revert(katalog): Anikiga, Eleceed, TonizuToon calisan ayara geri alindi
- `6c2853d` fix(oto-tamir): kuyruktan 160 kaynak denendi
- `1053553` fix(oto-tamir): kuyruktan 160 kaynak denendi
- `9183fbd` fix(katalog): 1.6.136 raporu tamiri (7 kaynak)
- `f01ee6d` fix(katalog): 6 Madara kaynagina chapterAjaxUrl
- `dc915af` fix(katalog): 3 domain tasinmasi, 9 yonlenen/park kaynak dead isaretlendi
- `6b2ecd9` fix(tr): golgebahcesi manifest API, 3 liste secici, jiangzaitoon domain
- `e46785e` fix(katalog): cihaz testinin 6 karari uygulandi
- `f2c8cf1` fix(tr): 11 kaynak duzeltildi, 13 kaynak durumu isaretlendi

## 5. Test geçmişi

`test-kayitlari.md` tablosu: 5 veri satırı (dosya 11 satır, 3'ü başlık/ayraç).

| Zaman (UTC) | Toplam | Geçti | Düştü | CF | Dosya |
|---|---|---|---|---|---|
| 2026-11-16T18:40:43.806Z | 297 | 57 | 236 | 4 | `kototoro-source-test-1794854443.json` |
| 2026-11-17T06:12:56.918Z | 566 | 227 | 322 | 17 | `kototoro-source-test-1794895976.json` |
| 2026-11-17T15:03:39.287944Z | 74 | 19 | 55 | 0 | `kototoro-source-test-1794927819.json` |
| 2026-11-17T15:11:40.544982Z | 63 | 51 | 12 | 0 | `2026-11-17T151140Z-ucpaket.json` |
| 2026-11-17T15:44:26Z | 85 | 1 | 81 | 0 | harness-belirsiz |

En yeni 4 satır: 06:12 (566/227/322/17), 15:03 (74/19/55/0), 15:11 (63/51/12/0), 15:44 harness (85/1/81/0).

## 6. Kalan iş

- **Tamir kuyruğu:** 1168 kayıt (`depo/tamir-kuyrugu.json`, `toplam` 1168 = `kayitlar` 1168).
- **Motor failed:** 1145 (defterdeki 1357 failed'ın motor kısmı; katalog tarafı 212).
- **Cihaz testi bekleyenler:** 57 unknown (katalog 55 + motor 2), pending 0. Ayrıca `test` paketindeki 37 kayıt hâlâ `unknown`.
- **Hedef açıkları:** 26 gerekçesiz failed/dead kayda tek cümlelik neden yazılmalı; test paketi sınıflandırılmalı; "harness-belirsiz" koşusunun ham dosyası `data/testler/` altına konmalı.
- **Katalog belirsizleri:** 55 katalog kaydı harness ile `active`/`failed` ayrımına alınmayı bekliyor (HEDEF §6/1).
