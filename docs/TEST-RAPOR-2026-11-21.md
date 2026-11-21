# Kototoro tam tarama raporu — 2026-11-21

Ölçüm: `tools/harness/run.sh` (Kototoro'nun kendi masaüstü çalışma zamanı + bizim yayındaki APK'lar).
Kapsam: 6 paketin tamamı, **747 id / 739 ölçülebilir domain**. Ölçüt: `list>0 && chapters>0 && pages>0`;
sayfa listesi HTML dönerse geçmiş sayılmaz (bu turda hiç tetiklenmedi: 0 satır).

## Paket tablosu

| Paket | Ölçülen | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| tr | 48 | 37 | 11 | %77 |
| tr18 | 4 | 2 | 2 | %50 |
| global | 243 | 65 | 178 | %27 |
| global18 | 283 | 21 | 262 | %7 |
| test | 111 | 0 | 111 | %0 |
| test18 | 50 | 2 | 48 | %4 |
| **Toplam** | **739** | **127** | **612** | **%17** |

Ham veri: `.work/tam/sonuc.json`, log'lar `.work/tam/<paket>.log`.

## Hata sınıfları

| Sınıf | Sayı | Ne demek |
|---|---:|---|
| `UnknownHostException` | **301** | DNS çözümlenemedi. **301'in 301'i katalogda kayıtlı** → yerel ISP DNS bloğu (TR). DoH ile curl 301/403 dönüyor, yani site sağlam. |
| `KATALOG_DISI` | **243** | **DÜZELTME:** hayalet değiller. 244 id'nin tamamı motor (`PulsarKotatsuSource`) kaynağı ve paketlerde örneği kuruluyor (HARNESS_DUMP ile TR 48/48, GLOBAL 245/245 doğrulandı). Harness motor kaynaklarını `domain`/`baseUrl` ile eşleştirdiği için (`domain=null`, `baseUrl=""`) test edemiyor. |
| `SocketTimeoutException` | 20 | 6 paralel işçi + zayıf bağlantı; tekrar denenmeli. |
| `UnsupportedOperationException` | 20 | Motorun `@Broken` kaynağı (aynı host'lu katalog kaydı yok). |
| `KAPSAM_DISI` | 12 | Kaynak başka pakette yayında; test yanlış pakette koştu (ölçüm hatası, kaynak hatası değil). |
| `bölüm listesi boş` | 6 | Gerçek arıza (liste var, bölüm yok). |
| `popüler liste boş` / boş hata | 9 | Gerçek arıza. |
| `SunCertPathBuilderException` | 1 | Sertifika zinciri. |

`list=0` olan 600 kaydın dağılımı: 301 DNS + 243 hayalet + 20 timeout + 20 @Broken + 12 kapsam dışı ≈ 596; kalan ~4 gerçek liste arızası.
`pages=0` (liste+bölüm çalışıyor): yalnız **6** kaynak — yani okuyucu tarafı büyük ölçüde sağlam.

## Yorum

1. **Asıl sorun kaynaklar değil, DNS.** 18+ paketinin %79'u (223/283) Türkiye ISP DNS'inde çözümlenmiyor.
   Kaynak config'lerinde `dnsOverHttps` alanı var ama katalogda **yalnız 1 kayıtta** dolu.
   301 kayda DoH eklendiğinde bu sınıfın tamamı test edilebilir hale gelir.
2. **Paket listeleri şişkin.** 747 id'nin 243'ü hayalet: katalogda karşılığı yok, motorda örneği yok.
   Gerçek yayın kapasitesi ≈ 504 kaynak. Hayaletler test havuzunu ve paket sayaçlarını kirletiyor.
3. Gerçek içerik arızaları az: ~16 liste + 6 okuyucu. Bunlar tamir edilebilir.

## Sıradaki işler

- (A) 301 DNS'li kayda `dnsOverHttps: https://cloudflare-dns.com/dns-query` ekle → build → aynı 301'i yeniden test et.
- (B) ~~Hayalet id temizliği~~ — **iptal**: 244 id motor kaynağı, silmek gerileme olur. Yerine: harness motor kaynaklarını id ile eşleştirebilsin.
- (C) 20 `@Broken` motor kaynağı için katalog karşılığı yaz (bugün 6'sı yapıldı, kalanlar ölçülü).
- (D) 20 timeout'u tek işçiyle tekrar dene.

## Doğrulama

```
grep -c '^{"domain"' .work/tam/*.log
python -I -X utf8 -c "import json;print(len(json.load(open('.work/tam/sonuc.json',encoding='utf-8'))))"
```

## DoH sonrası (301 kaynak)

Ölçüm: aynı harness, build `80e3137` APK'ları; katalogdaki `dnsOverHttps: https://cloudflare-dns.com/dns-query` (commit `55dfa9e`) ile.
Kapsam: ilk taramada `UnknownHostException` alan **301 (domain, paket) çifti** — global 78 + global18 223.
`doh-gerekli.txt` 300 tekil domain tutuyor; 301. çift `mundomanhwa.com`'un iki pakette de bulunmasından geliyor.
Ölçüt aynı: `list>0 && chapters>0 && pages>0`.

**Sonuç: 0/301 → 192/301 (%64).** `UnknownHostException` sınıfı 301 → 3.

### Paket tablosu

| Paket | Test | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| global | 78 | 70 | 8 | %90 |
| global18 | 223 | 122 | 101 | %55 |
| **Toplam** | **301** | **192** | **109** | **%64** |

### Kalan hata sınıfları (301 çift)

| Sınıf | Sayı | Not |
|---|---:|---|
| `SocketException: Connection reset` | 95 | DNS değil: TLS bağlantısı sıfırlanıyor. `curl --doh-url ...` ile de aynı (`curl: (35) Recv failure: Connection was reset`) → SNI/ISP engeli. |
| `UnknownHostException` | 3 | topcomicporno.com, truyenhentai18.net, truyenhentaiz.net — DoH'a rağmen çözümlenemedi. |
| `sayfa=0` (hata yok) | 4 | xoxocomic.com, hentaizone.me, miku-doujin.com, pawchive.pw — liste ve bölüm var, sayfa boş. |
| `bölüm listesi boş` | 3 | mangahere.onl, mangaonline.fun, mangatoday.fun |
| `SocketTimeoutException` | 2 | manhwaclub.net, toontop.io |
| `IOException: Cloudflare bypass currently disabled` | 1 | novelstreams.com |
| `popüler liste boş` | 1 | one-manga.com |

Notlar:
- `OK` (hata alanı boş) 196 çiftin 4 tanesi sayfa üretmediği için geçmedi; kalan 192 geçti.
- Kapsam dışı ek koşular: test'te 2 (`KAPSAM_DISI`), test18'de 2 (`UnsupportedOperationException`), global18'de 1 (`toomtam-manga.com`, `KAPSAM_DISI`). Bunlar ilk taramada da aynı sınıftaydı, 301'e dahil değil.
- Ölçüm sırasında `origin/main` `87cdf77`'ye ilerledi (`73d526e`: motorda sistem DNS düşünce otomatik DoH yedeği). Bu bölümdeki sayılar katalog düzeyindeki DoH düzeltmesini ölçen `80e3137` APK'larına aittir; motor düzeyindeki yedek bu ölçüme dahil değil.
- Ham veri: `.work/tam2/sonuc.json` → `pulsar-v2/data/testler/2026-11-21-doh-sonrasi.json`; log'lar `.work/tam2/<paket>.log`.

## tlsFragment sonrası (95 kaynak)

Ölçüm: aynı harness; `df7d5ab` katalog düzeltmesi + build `44929442723` APK'ları (versionCode 264).
Kapsam: DoH sonrası `SocketException: Connection reset` alan **95 domain** (`.work/tam/tlsf-gerekli.txt`);
paket dağılımı global 2 + global18 93 (`euphoriascan.com` global18'de ölçüldü).
Katalogda 95 domainin 95'i de bulundu (`CONFIG=95`, bulunamayan 0); her kayda yalnız
`"tlsFragment": true, "tlsFragmentSize": 1` eklendi. Ölçüt aynı: `list>0 && chapters>0 && pages>0`;
`HARNESS_SAYFA_HTML` hiç tetiklenmedi (0 satır).

**Sonuç: 0/95 → 94/95 (%99).** `SocketException: Connection reset` sınıfı 95 → 0.

### Paket tablosu

| Paket | Test | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| global | 2 | 2 | 0 | %100 |
| global18 | 93 | 92 | 1 | %99 |
| **Toplam** | **95** | **94** | **1** | **%99** |

### Kalan hata sınıfları (95 domain)

| Sınıf | Sayı | Not |
|---|---:|---|
| `pages=0` (hata yok) | 1 | metarthunter.com — liste 60, bölüm 18 var, sayfa 0. TLS değil; okuyucu seçici arızası, tekrar koşuda aynı (list 60 / bölüm 18 / sayfa 0). |

İlk 5 domain (önce → sonra, list/bölüm/sayfa):

| Domain | Önce | Sonra |
|---|---|---|
| de.fsicomics.com | reset | 19/1/22 |
| de.wporncomics.com | reset | 20/1/44 |
| doujins.com | reset | 4/1/37 |
| e621.net | reset | 73/1/1 |
| eahentai.com | reset | 46/40/42 |

Ham veri: `.work/tam3/sonuc.json` → `pulsar-v2/data/testler/2026-11-21-tlsf-sonrasi.json`; log'lar `.work/tam3/<paket>.log`.

## Timeout tekrarı (20 kaynak)

Ölçüm: aynı harness, yayındaki APK'lar **v1.6.265 (versionCode 265)** — `.work/tam4/apk/<paket>.apk`.
Kapsam: ilk taramada `SocketTimeoutException` alan **20 domain** + DoH tekrarında aynı sınıfa düşen
2 domain (`manhwaclub.net`, `toontop.io`) = birleşik veride **22 domain**. Ölçüt aynı:
`list>0 && chapters>0 && pages>0` ve `hata` boş.

**Sonuç: 20 kaynakta 0/20 → 16/20; birleşik 22 domainde 18/22 (%82).**

### Paket tablosu

| Paket | Test | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| global | 1 | 1 | 0 | %100 |
| global18 | 16 | 16 | 0 | %100 |
| tr | 1 | 1 | 0 | %100 |
| test18 | 4 | 0 | 4 | %0 |
| **Toplam (22)** | **22** | **18** | **4** | **%82** |

### Kalan 4 kaynak

| Domain | Paket | Sonuç | Sınıf |
|---|---|---|---|
| 20.allhen.online | test18 | 78/17/0 | sayfa 0 (timeout bitti) |
| comics18.org | test18 | 24/1/0 | sayfa 0 (timeout bitti) |
| 3hentai.net | test18 | 0/0/0 | popüler liste boş |
| ohjoysextoy.com | test18 | 4/0/0 | bölüm listesi boş |

Timeout sınıfı bu 22 domainde 0'a indi; kalan 4'ü farklı sınıflarda (ikisi sayfa üretmiyor,
ikisi liste/bölüm boş). Geçenler `source-status.json`'da **terfi ettirilmedi** (kapsam dışı).

Ham veri: `.work/tam4/sonuc.json`; log'lar `.work/tam4/<paket>.log`; APK/JAR/sınıf dizinleri
`.work/tam4/manifest.json`.

## Hayalet iddiasının denetimi (242 kayıt) — defter değişikliği YAPILMADI

Üç JSON birleştirildi (domain başına en iyi sonuç), `hata == "KATALOG_DISI"` → **242 domain**
(`.work/tam/hayalet-son.txt`, 242 satır). Bu domainler `source-status.json`'da **244 id**'ye
karşılık geliyor (`mangasusuku.com` ve `mangaread.org` ikişer paket id'si taşıyor).
İddia: bu id'lerin "motorda örneği yok". Denetim bunu **çürüttü**:

1. v265 APK'larında `HARNESS_DUMP=1` ile paket başına kurulan kaynak örnekleri döküldü.
   Paket id sayısı ile kurulan örnek sayısı **birebir eşit**:
   TR 48/48, TR18 4/4, GLOBAL 245/245, GLOBAL18 283/283, TEST 116/116, TEST18 51/51.
2. 244 id'nin **244'ü de** dökümde `PulsarKotatsuSource` örneği olarak var
   (ör. `4234251771760310115` MangaRead, `1608873353115070792` MangaEffect,
   `1608885718281838973` MangaSusuku).
3. `KATALOG_DISI` bir harness eşleştirme yanılgısı: motor kaynakları `domain=null`,
   `baseUrl=""` bildiriyor; harness yalnız katalogdan türetilmiş id ile eşleştiriyor, bu id'ler
   ise `pulsar-kotatsu/<AD>/<dil>` hash'i. Yani kayıt yokluğu değil, **eşleşememe**.
4. `PulsarSourceFactory.createSources()` zaten `all.filter { it.id in allowed }` yapıyor:
   paket listesindeki her id kurulan bir kaynağa karşılık gelmek zorunda; sayaç eşitliği bunu doğruluyor.

Bu yüzden `source-status.json` üzerinde `dead/kapali/sorun/packages` değişikliği **yapılmadı**,
pipeline (`06_prepare_assets.py` → `merge` → `status` → `embed`) **koşulmadı**, commit/push/build
**atılmadı**. 242 id'yi kapatmak, çalışan 244 kaynağı paketlerden silmek olurdu.
Not: bu 244 id'nin 20'si `source_map.json`'da `broken=true` (upstream `@Broken`); ayrı iş olarak
değerlendirilmeli.

Doğrulama: `grep -c '^# KAYNAK ' .work/ghostchk/<paket>-dump.txt` (global 245, global18 283,
test 116, test18 51, tr 48, tr18 4); `grep ' id=' .work/ghostchk/*-dump.txt`.

## Motor kaynakları (id/ad eşleştirmesi)

Ölçüm: `tools/harness/run.sh`; yayındaki **v265** APK'ları (`.work/tam4/apk/`, 21:07 snapshot).
Kapsam: paketlerdeki **244 motor kaynağı** (`PulsarKotatsuSource`), `@name:<kaynak adı>` ile
ad üzerinden eşleştirildi. Ölçüt aynı: `list>0 && chapters>0 && pages>0` ve `hata` boş.

Kod: `tools/harness/Harness.java` `findSource` (satır 342) `@name:` modu; motor kaynağı yalnız
yeni suspend API'yi uyguladığı için `callSuspend` (satır 444) ile `getPopularManga` /
`getMangaUpdate` / `getPageList` çağrılıyor (satır 206'daki `engine` dalı). Katalog
kaynaklarının legacy yolu değişmedi.

### Paket tablosu

| Paket | Test | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| tr | 10 | 7 | 3 | %70 |
| tr18 | 0 | 0 | 0 | — |
| global | 95 | 83 | 12 | %87 |
| global18 | 22 | 22 | 0 | %100 |
| test | 90 | 10 | 80 | %11 |
| test18 | 27 | 11 | 16 | %41 |
| **Toplam** | **244** | **133** | **111** | **%55** |

`source_map.name` görünen adla eşleşmeyen 17 kaynak `source_map.title` ile (2 tanesi
baseUrl host'u ile) yeniden koşuldu ve sonuç birleştirildi; 244 satırın 244'ü de tekil.
`tr18` paketinde KATALOG_DISI motor kaynağı yok (0).

### Hata sınıfları

| Sınıf | Sayı |
|---|---:|
| `HttpStatusException` | 39 |
| `popüler liste boş` | 21 |
| `NotFoundException` | 13 |
| `sayfa 0` (hata yok) | 13 |
| `IOException` (`Cloudflare bypass currently disabled` dahil) | 9 |
| `UnknownHostException` | 5 |
| `bölüm listesi boş` | 4 |
| `SocketTimeoutException` | 3 |
| `CertificateExpiredException` | 2 |
| `ProtocolException` | 1 |
| `SSLException` | 1 |
| **Geçti (hata yok)** | **133** |

Notlar:
- `source_map.json`'da `broken=false` süzgeci uygulansaydı liste **224** kalırdı. 244 hedefi
  ve önceki bölümdeki 244 id için **20 `@Broken` kaynağı da** koşuldu. Bunlardan
  `RIZZCOMIC` ve `ANIBEL` geçti; kalan 18'i hata verdi.
- Motor kaynakları `HttpSource`'un legacy `fetch*` yolunda `UnsupportedOperationException`
  atıyor; bu yüzden harness'a suspend yol eklendi. Ayrıca uygulamanın gömülü `parser-api`
  sürümü APK'nın `kotatsu-parsers-redo` sürümünden eski (`newParserInstance(MangaSource)`
  vs `MangaParserSource`); koşuda `PARSERS_JAR` (kotatsu-parsers-redo.jar) sınıf yolunun
  başına eklendi. `tools/harness/run.sh` depoda izlenmiyor (untracked).
- `SODSAIME` (Thai görünen ad) ve `TRUYENTRANHDAMMYY` yalnız baseUrl host'u ile test
  edilebildi: APK'da görünen adları `???????` / `Truy?n Tranh ?am M?` (Unicode kaybı),
  `source_map.name` ile eşleşmiyor.
- Ham veri: `.work/motor/sonuc.json` → `pulsar-v2/data/testler/2026-11-21-motor-tarama.json`;
  loglar `.work/motor/t4-*.log`.
