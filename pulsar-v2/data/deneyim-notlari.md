---
# Deneyim notları — 1.6.30 → 1.6.33

Bu dosya, tekrar edilmemesi gereken keşifleri tutar. Her satır bu oturumda gözlenmiş
kanıta dayanır; kanıtsız iddia yok.

## 1. Sürüm doğrulaması (en pahalı hata)

- Cihaz raporunun hangi sürümden geldiğini ASLA varsayma. Bu oturumda 1.6.31 sanılan
  rapor, aslında 1.6.31 öncesi bir sürümdendi; teşhis yanlış yere gitti.
- Doğrulama üç kanıtla yapılır:
  1. `index.min.json` içindeki `version` / `code` alanı.
  2. Raporda o sürüme özel tanı satırı var mı (`TANI2`, yeni hata mesajları).
  3. APK'nın içindeki gömülü katalog: `unzip` → `classes*.dex` içinde `eyJ...` Base64 →
     çöz → yeni config anahtarları orada mı.
- Örnek: 1.6.31 APK'sında `diag` 5 domainde, `rscChapterUrl` slept+lunarx'te çıktı;
  rapor bunların hiçbirini göstermiyordu → rapor eski sürümdü.

## 2. Derleme hattı

- Tek doğru kaynak `pulsar-v2/data/catalogue.json` (109 kayıt).
- Hat: `scripts/06_prepare_assets.py` (domain+dil tekilleştirme, 94) → `pulsar merge`
  (klon birleştirme, 62) → `pulsar embed` (Base64 → `PulsarData.kt`) → APK.
- `extension/src/main/assets/catalogue.json` elle düzenlenmez; hat onu ezer.
- CI (`build-extension.yml`) yalnız `workflow_dispatch`; push tetiklemez:
  `gh workflow run build-extension.yml --ref main`.
- CI `PulsarData.kt`'yi commit'lemez; repodaki Kotlin gömülü veri bayat kalır.

## 3. Ayrıştırıcı dersleri

- **Gövde bir kez okunur**: OkHttp `response.body.string()` ikinci çağrıda boş döner.
  Dallanma kontrolü gövde okunmadan ÖNCE yapılmalı.
- **Sessiz seçici hatası**: config'teki `readerSelector` siteye uymuyorsa 0 döner ve
  hata görünmez. nyxscans'ta `div#readerarea img` vardı, sayfada öyle bir kap yoktu;
  seçici kaldırılınca 47 görsel HTML'den okunur hâle geldi. Şüphelenince önce config.
- **Tek parçalı bölüm yolu**: `/<slug>-chapter-50/`, `/<slug>-bolum-1/` biçimleri
  `oneSegmentPrefix` ister; parça sayısı ≥3 kuralı bunları eler.
- **SManga.url göreli olmalı**: mutlak URL verilirse host `site.comhttps` olur.
  TrManga'yı düzelten şey `mangaDetailsParse` içinde `url`'i korumaktı.
- **Kapak proxy'si**: `/api/image-proxy?url=<CDN>` 403 dönüyorsa `url` parametresi
  çözülüp CDN doğrudan kullanılır (Referer'lı CDN 200).
- **Tek `User-Agent`**: `super.headersBuilder()` üstüne `add()` çift başlık üretir;
  bazı CDN'lerde 403. `removeAll("User-Agent")` + tek UA.

## 4. Gömülü veri desenleri (kanıtlı)

- **Next.js RSC**: `self.__next_f.push([1,"…"])` kaçışlı yükü. `rscText` çözer,
  `balancedArray`/`arrayAfter` ile dizi okunur. Bölümler: `chapters[]`
  (`number`/`chapter_number`, `chapter_title`). Liste kartları: `siteUrl` + `title.romaji`
  + `coverImage.large` (lunarx.to, 90 kart).
- **Qwik**: `<script type="qwik/state">`; görseller metin içinde (xcomic 33).
- **ts_reader.run**: nabicix bölüm görselleri bu JSON'un `images` dizisinde.
- **Ham metin yedeği**: DOM'da görsel yoksa `rawImages` regex ile adres çıkarır;
  ölçüm xcomic 35, koreli 33 aday.
- **JSON bölüm API'si**: mangaball.com `GET /api/v1/title/chapter-listing?title_id=<24hex>…`
  `data[]` (`name`, `number`, `url`). Kod: `chapterApiUrl` + `chapterApiIdPattern`.
- **JSON arama API'si**: lunarx araması sitede çalışmıyor (istemci tarafı); gerçek uç
  nokta `https://api.lunarx.to/api/manga/search?query=<q>`, yanıt `{"manga":[...]}`
  (`slug`, `title`, `cover_url`). Site yolu yanıtta YOK → `searchJsonPathPrefix`
  ile `/manga/<slug>` kurulur. Ayar: `searchUrl` + `searchJsonItems=manga` +
  `searchJsonUrl=slug` + `searchJsonTitle=title` + `searchJsonPathPrefix=/manga/`.
- **Ders**: arama sayfası 200 dönüp sonuç üretmiyorsa sayfa değil API aranır; HTML'de
  `API_BASE` / `fetch(\`${...}/api/...\`)` izleri uç noktayı verir.

## 5. Çözülemeyenler (avı kapandı)

- **Slept Manga sayfalar**: `GET /api/chapters/{slug}/{bölüm}/images` var ama gerçek
  görseller yalnız `x-turnstile-token` (Cloudflare Turnstile) ile dönüyor. Tokensız
  istek 200 + 5 adet `/api/watermark` yer tutucusu.
- **Sunset Manga**: şifreli okuyucu (`data-token` + `toon-reader.js`).
- **araznovel**: detay sayfası Cloudflare Turnstile bot kapısı (5.439 bayt, tek script
  `challenges.cloudflare.com/turnstile`); `admin-ajax.php` `action=ao_bot_gate_verify`
  doğrulamasından sonra `window.location.reload()`. Eklenti bu kapıyı geçemez.
- **Lunar Manga sayfalar**: bölüm sayfası 200 / 78.722 bayt ama HTML'de tek `<img>`
  (tema bannerı) ve görsel adresi yok; `?lang=` fark etmiyor. Sayfada `/api/page-locks`
  ve `/api/proxy/m/` izleri var; görseller istemci tarafında, kesin uç nokta doğrulanamadı.

## 6. Alan adı taşınmaları

- `ragnarscans.net` → `ragnarscans2.com`, `mangaruhu.com` → `mangaruhu.net` (301).
- `baseUrl` güncellenir, `domain` alanı KORUNUR: kaynak kimliği `pulsar/{domain}/{lang}`
  hash'inden üretilir, domain değişirse kullanıcının kitaplığı kopar.

## 7. Ajan işletimi

- "HEAD'i kontrol et" deme, SHA ver: kendi commit'in HEAD'i kaydırır. Bir ajan tam bu
  yüzden yanlış commit'i okudu.
- `git diff --stat` fazla dosya gösterebilir; bunlar önceki oturumun kirli ağacıdır.
  Ajanın kendi yazdığı dosya sayısını ayrıca doğrula.
- Okuma, yazma ve doğrulama ayrı ajanlarda: doğrulayıcı bu oturumda iki gerçek hata
  yakaladı (gövdenin iki kez okunması, char sabitinden kaynaklı sahte parantez dengesizliği).
---

## 8. Yerel testçi (source-host) ve aldatıcı NO_SOURCES

Kototoro'nun kendi kaynak testini masaüstünde koşturmak istediğinde ilk duvar `sources` alt komutudur:

- `sources` platformu HİÇ başlatmaz (`SourceHostCli.kt:20-25`); Injekt/Koin kurulmaz. Fabrikası `Injekt.get<Application>()` çağıran bir eklenti (bizim `PulsarSourceFactory.kt:38-39`) bu yüzden boş liste döner ve `MihonJarRegistry.kt:138` **NO_SOURCES** fırlatır. Bu eklentinin suçu değil, CLI'nin sınırıdır; aynı fabrika cihazda sorunsuz çalışır.
- NO_SOURCES'un üç kaynağı: `createSources()` null / öğe null (:132-133), liste boş (:138), öğe `CatalogueSource` değil (:140). Sınıf yüklenemezse mesaj `CONSTRUCTION_FAILED` olur (:162-168). Yani NO_SOURCES "sınıf bulunamadı" DEMEK DEĞİLDİR.
- `HttpSource`, `CatalogueSource` uygular (`HttpSource.kt:35`); tip kontrolü normalde geçer.
- Gerçek test yolu `serve`: `platformClass` zorunlu ve varsayılanı yok (`SourceHostConfig.kt:9`); aday `org.skepsun.kototoro.desktop.compat.MihonDesktopPlatform`. Platform `initialize` içinde Koin + `Injekt` kurar (`MihonDesktopPlatform.kt:90-94`), `NetworkHelper` bağlar (:121). Ama **`preferenceDirectory` verilmezse** `initialize()` boş sürüme düşer ve platform "error"da patlar (`:58`) — config'te bu alan şart.
- `Application` bağlaması repodaki koddan doğrulanamadı; dış `createAppModule(app)`'a devredilmiş (`:91`). `serve` altında `Injekt.get<Application>()` çalışır mı sorusu ancak çalıştırarak kapanır.
- APK→JAR: `ApkExtensionConverter` kullanılır; `inspect` düz metin `AndroidManifest.xml` beklediği için APK'ya doğrudan verilirse `INVALID_MANIFEST` döner. jshell ile çağırırken `-R-Xmx2000m` şart, yoksa "State engine terminated" (OOM).

## 9. Aralıklı 403 (Amanga Planet CDN)

Aynı görsel adresi 10 GET'in ~4'ünde 200, ~6'sında 403 dönüyor. User-Agent (6 varyant), Referer ve çerez değiştirmek sonucu değiştirmiyor; `www.` yolu 404. Yani engel kalıcı bir kimlik kontrolü değil, kaynak taraflı aralıklı reddetme.

Çözüm yeniden deneme: `PulsarSource.client` içine interceptor eklendi (1.6.35). Yalnız `GET` + `403` için en fazla 3 deneme, artan bekleme (250/500/750 ms); POST isteklerine dokunmaz. Kalıcı çözüm değildir ama tek seferlik düşmeleri kapatır.

## 10. 1.6.44–1.6.45 dersleri

- **RSC bölüm dizisi**: Nyx'te bölüm listesi `initialChapters:$R[73]=[$R[74]={slug:"chapter-60",number:60,...}, ...]` biçiminde. Başlık deseni `$R[n]=` önekini kabul etmeli; dizi sınırı köşeli parantez derinliği sayılarak bulunmalı. "İlk `]`" ile kesmek 60 bölümü 0'a düşürüyordu. Ön sınama: indirilmiş HTML üzerinde aynı algoritmayı `python -I -c` ile koştur; slug ve number sayısı 60 çıkmalı.
- **Cihaz raporu sürümü**: `diag` anahtarı 466efd1'de eklendi, fc53b2f'de silindi. TANI2 satırı içeren rapor ≤ 1.6.34'tür. Yayındaki APK'nın `assets/catalogue.json`'unda `diag` anahtarının yokluğu bunu doğrular. Sürüm numarası repoda tutulmaz (CI run number'ından gelir), o yüzden sha ile bağ kurulur.
- **Katalog tekilleştirme**: 109 kayıt, 15 mükerrer (aynı domain+lang). `06_prepare_assets.py:138-150` dosya sırasındaki ilk kaydı tutar. Temizlik 109→94; `total_count` alanı da güncellenmeli. Kanıt: CI sonrası index'te paket başına id/ad listeleri birebir aynı (tr 30, tr18 4, global 361, global18 134).
- **`pulsar sweep`**: `details` HATASI da (harness imzalı hatalar hariç) sıradaki esere geçirir, en fazla 3 eser. `eser` sütunu hangi eserin denendiğini gösterir. 0 bölümlü eser artık "bozuk" sayılmaz (tenshimanga 39 bölüm / 61 sayfa).
- **Yerel sınama sınırı**: harness yalnız catalogue kaynaklarını sınar; engine kaynakları `newParserInstance(MangaSource)` ABI uyuşmazlığı yüzünden çalışmaz.
