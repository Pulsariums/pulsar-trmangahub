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
- **Yerel sınama sınırı (aşıldı, bkz. 14)**: harness eskiden yalnız catalogue kaynaklarını sınıyordu; engine kaynakları `newParserInstance(MangaSource)` ABI uyuşmazlığı yüzünden çalışmıyordu. `--engine` artık child-first yükleyici + Maven parser JAR'ı ile bunu aşıyor.

## 11. Yayın listesi `source-status.json`'dan gelir

- `tools/pulsar/src/status.rs::ensure_all` eskiden yalnız eksik kaydı ekliyordu (`entry(...).or_insert_with`). Katalogda dil/domain değişince eski id yayında kalıyordu (mangaball: `tr` → `en`, tr paketinde 1.6.46'ya kadar göründü).
- Düzeltme (`9921224`): her çalıştırmada kimlik alanları (id/kind/title/lang/nsfw/domain/packages) `source_map.json`'dan güncellenir, haritada olmayan id `retain` ile budanır; health/device/note korunur.
- Yayına yalnız `state=active` kaynaklar girer (`generate_repo.py`). Katalog değişikliğinden doğan yeni id `unknown` başlar ve sağlık ölçümü yapılmadan global pakete girmez.
- Kanıt: 1.6.47'de tr 30→29, diğer paketlerde id farkı yok; budanan 32 kayıt zaten yayında değildi.

## 12. Liste adımı avı ve ölü ayrımı (1.6.49)

- **`pulsar probe` kör noktaları**: sayım `(manga|seri|series|comic|manhwa|webtoon)/slug` kalıbına bakıyor. Tek segmentli `/slug` (okutoon), `/archive/N/` (panda.chaika) ve `/c/slug` (globalcomix) linklerini göremiyor; sayfa 200 olsa bile `empty` yazıyor. Bu üçünde karar "sayfa 200 + gerçek link sayısı" ile verildi (24 / 100 / 144).
- **Jsoup kendini bulmaz**: `el.selectFirst("a[href]")` yalnız ALT öğelere bakar. Kartın kendisi `<a class="series-card" href="/slug">` ise liste 0 çıkar. Düzeltme (`3c532ae`): önce `el.tagName()=="a"` kontrolü; başlık sırası heading → `title` → `aria-label` → metin → `img[alt]`.
- **Kesin ölü işareti**: katalogda `"dead": true`. `status.rs::packages_for` boş paket döner, durum `dead` olur; kaynak hiçbir APK'ya girmez. Kanıtlı ölüler: guildknives.com (GoDaddy park), noxscans.com ve mangakazani.com (ParkLogic), mangaoku.info ("satılıktır"), alliedfansub.net (177 bayt boş), jiangzaitoon.icu (502, .com park), fuchscans.com (NXDOMAIN), juratempe.st (YouTube'a yönlendiriyor).
- **Cloudflare / DDoS-Guard** (`sorun: "cloudflare"`): sadscans.com, ravenscans.org, mangagezgini.online, millascan.com, mangadot.net, manga-tr.com. `tr_sorunlu` paketine giderler.
- **Cihaz verisi tek yönlüdür**: rapor yalnız düşen kaynakları yazar, geçen kaynağın eski `fail` etiketi silinmez. Bu yüzden `state` kuralı adım bazlı: cihazda `list` (veya adım bilgisi yok) + health `ok` → `pending`; `pages/details/search` düşmesi kaynağı yayından çıkarmaz (`d48d10a`, 1.6.47→1.6.48'de tr 29→20 kaybının sebebi buydu).
- **Belirsiz ≠ ölü**: anti-bot/SPA engeli (nyxmanga, mangasiginagi, esomanga, mangacix, namicomi, mindafansub, toonhane, summertoons, piedpiperfansub) ölü sayılmadı; yalnız park/NXDOMAIN/satılık kanıtı `dead` yapar.

## 13. Tek komutla tam zincir testi (`pulsar sweep`, 1.6.49)

- **Komut**: `tools/pulsar/target/release/pulsar.exe sweep --lang tr --engine`. `index.min.json` içinden `lang=tr` paketlerini (tr, tr18, tr_sorunlu) bulur; her APK'yı Kototoro'nun `DexConvertCliKt` sınıfıyla geçici JAR'a çevirir; `source-host serve` ile adımları koşar. `--java`/`--app` verilmezse `%USERPROFILE%\Desktop\Kototoro` altında `runtime/bin/java.exe` + `app` aranır. Seçim: `--lang`, `--nsfw 0|1`, `--name <parça>`, `--site <domain>`, `--limit`, `--out`; ortak: `--catalogue`, `--index`, `--apk-dir`, `--status`, `--timeout`, `--engine`, `--debug`.
- **Adımlar cihazla aynı sırada**: list → cover → search → details → chapters → pages. Arama cihazın iki sorgusunu dener: `"a"`, `"one"` (`SourceTestModels.kt`). Kapak `cover` işlemiyle gerçekten indirilir (`/result/artifact/byteSize`). `random` yerel protokolde yok, test edilmez.
- **Sonuç (2026-11-14, 1.6.49 APK'ları, `--engine` ile)**: 45 yayındaki tr kaynağı; **28 sağlam, 11 gerçek bozuk, 6 yerel harness dışı**. Gerçek bozuklar ve `sebep` sütunu: lunarx.to (pages, sayfa listesi boş), webtoonoku.org (cover, INVALID_ARGUMENT), opiatoon.shop (details, `IllegalStateException: TANI kod=200 …/giris-yapmalisiniz/` — oturum kapısı), manga.araznovel.com (details, `TANI …/series/… len=5456` — Turnstile kapısı), manga-tr.com (list, `HttpException: HTTP error 403`), anikiga.com (details, admin-ajax 400), araznovel.com (list, admin-ajax 404), mangaruhu.com (list, admin-ajax 400; ikinci kayıt pages boş), shadowceviri.blogspot.com (search, arama boş), sleptmanga.com.tr (pages, sayfa listesi boş). Rapor: `pulsar-v2/data/test-report-tr-all.csv` (45 satır, 45 tekil id).
- **`sebep` alanı**: `SOURCE_FAILURE <rid> <Call>` sonrası yığın izinden okunur. RxJava sarmalayıcısı (`rx.exceptions.OnErrorThrowable…`) sebep sayılmaz; mesajı olan ilk gerçek istisna, yoksa ilk Rx dışı `Caused by:` satırı alınır (180 karakter). Ham yığın izi için `--debug` (istek başına en fazla 120 satır, stderr). Protokol düzeyinde dönen `INVALID_ARGUMENT` gibi hatalarda mesajın kendisi sebebe yazılır.
- **Engine kaynakları artık koşar**: 45'in **19'u** engine (status'taki `kind=engine` 13'ü; kalan 6'sı çağrı sırasında ABI imzasıyla yakalanır). `--engine` child-first yükleyiciyi devreye alır; ayrıntı bölüm 14. Kalan 6 harness: 5 Cloudflare köprüsü (mangadot, mangagezgini, millascan, ravenscans, sadscans) + tilkiscans (parser `suwayomi/tachidesk/server/ServerConfigKt` sınıfını arıyor, masaüstü host'ta yok).
- **Hedef listesi indeksten gelir**: `index.min.json` paketlerinin `sources[]` alanı `id`/`baseUrl`/`lang` taşır; host'un döndürdüğü ad `MIHON_<id>`. Katalog yalnız data-driven kaynakları kapsadığı için hedef üretiminde tek başına yetmez (45'in 13'ü kaybolur).
- **İki Windows tuzağı**: (1) `DexConvertCliKt` çıktısındaki `CONVERTED {...}` satırı geçerli JSON değildir — `output` alanındaki ters bölüler kaçışsızdır; `packageName`/`versionCode`/`sha256` alanları metinden ayrıştırılır. (2) Protokolde `Long` alanları ondalık string gelir (`byteSize`, `contentId`); `as_i64()` None döner.

## 14. Engine kaynaklarını yerelde koşmak (`--engine`)

- **Belirti**: engine kaynağında `list` düşer; yığın izinde
  `NoSuchMethodError: PulsarContext.newParserInstance(MangaParserSource)`,
  `Caused by` altta `Mihon runtime ABI failure`. Bu bir kaynak hatası değil, harness hatasıdır.
- **Neden**: `source-host` eklenti JAR'ını **parent-first** `URLClassLoader` ile açar. Host'ın
  kendi `parser-api` sürümü `newParserInstance(MangaSource)` (arayüz) taşır; eklenti ise
  `MangaParserSource` (enum) ile derlenmiştir. Cihazda eklenti child-first yüklendiği için
  çakışma görünmez; masaüstünde görünür.
- **Çözüm**: `tools/pulsar/java/ChildFirstPlatform.java` — `MihonDesktopPlatform`'u sarar,
  yalnız `org.koitharu.kotatsu.parsers.*` için child-first davranan bir yükleyici döndürür.
  `pulsar sweep --engine` bu sınıfı `javac` ile geçici dizine derler, `platformClass` olarak
  verir ve `-Dpulsar.engineJar=<APK→JAR>` geçer.
- **İkinci tuzak**: APK'nın dex'ten çevrilen JAR'ı, Kotlin arayüz varsayılan metotlarını
  `Methodref` sabitiyle taşır; masaüstü JVM bunu
  `IncompatibleClassChangeError: Method 'WebClient.httpGet' must be InterfaceMethodref`
  ile reddeder. Aynı rev'in Maven JAR'ı (`com.github.clquwu:kotatsu-parsers-redo:<ref>`)
  doğru `InterfaceMethodref` taşır. `-Dpulsar.parsersJar` bu JAR'ı gösterir; ilk kullanımda
  `pulsar-v2/.work/harness/` altına indirilir. `parsersRef` `extension/build.gradle.kts`
  ile aynı olmalı (şu an `59c033ecfd`).
- **Harness yanlış-pozitifi**: `stderr_has_harness` bu isteğe ait `SOURCE_FAILURE <rid>`
  bloğu yoksa artık `false` döner. Önce tüm stderr arabelleği taranıyordu; önceki kaynağın
  `NoClassDefFoundError` izi, sayfa listesi boş gibi protokol hatası olmayan düşüşleri
  yanlışlıkla `harness` yazıyordu (lunarx, webtoonoku, mangaruhu, sleptmanga).
- **Kalan harness**: Cloudflare köprüsü (5) `CloudflareInterceptor` içinde
  `suwayomi/tachidesk/server/ServerConfigKt` arıyor; sınıf masaüstü host'ta yok. Tilkiscans
  aynı sınıfı parser üzerinden arıyor. Bu kaynaklar cihazda Cloudflare çözücüsüyle ayrıca
  denenmeli.

## 15. Bozuk kaynak avı: dış parser sınırı (2026-11-14)

- **256 bozuk kaydın dağılımı**: TR paketlerindeki 11 bozuk kaydın 8'i bizim katalog, 3'ü dış engine; globalde bozukların neredeyse tamamı JitPack `kotatsu-parsers-redo` parser'ı. Yani global bozukların çoğu bizim kodumuzda değil, upstream'de. Tek tek tamir yerine canlı olanı katalog kaydına çevirmek gerekir.
- **Site taşınmaları (curl ile doğrulandı)**: `kenscans.com → kencomics.com` (yeni DOM: `div.card-group` 60, bölüm 17, ücretsiz bölümde `img[data-reader-page-image=true]` 42, arama `?searchTerm=`), `madarascans.com → .net` (`div.bsx` 30, bölüm `li[data-num]` 38, sayfa `ts_reader.run → images`). İki sitede de eski parser seçicileri 0; domain override tek başına yetmez.
- **JAR parser'ı düzeltmenin yolu**: eklenti parser'ı JitPack commit'inden alır (`parsersRef`); yerel fork yoksa seçici değişikliği APK'ya girmez. Bu yüzden canlı siteler katalog (data-driven) kaydına taşınmalı veya upstream'e yama gönderilmeli.
- **`parseChapters` kendini bulmaz**: `chapterSelector` doğrudan `<a>` eşleştiriyorsa (webtoonoku `a.chapter-box`) Jsoup alt öğe arar ve 0 döner. `parseList`'teki `el.tagName()=="a"` kontrolü `parseChapters`'a da eklendi (`EngineRegistry.kt`).
- **Sayfa API'si**: LunarX sayfaları HTML'de yok; `GET api.lunarx.to/api/manga/{slug}/{number}` → `data.images[]`. `PulsarSource`'a `pageApiUrl` + `pageApiIdPattern` + `pageApiItems` (noktalı yol) eklendi; config `catalogue.json` ve `alive_sources.json`'a yazıldı. Derleme/cihaz testi yapılmadı.
- **Seçiciyle çözülmeyenler**: manga-tr.com DDoS-Guard 403; mangaruhu.net bölüm HTML'inde görsel yok, REST uçları 403/404; sleptmanga.com.tr `/api/chapter/<id>` uygulama anahtarı istiyor (curl 403). Bunlar katalog seçicisiyle düzeltilemez.
- **WebtoonOku kapak hatası**: `itemSelector` içindeki `a[href*="/manhwa/"]` nav linklerini de alıyordu, kapak null kalıp `cover INVALID_ARGUMENT` veriyordu. `article.manga-item` + `a.chapter-box` + `div.reader-images img` yapıldı; spec `css` bloğuna da yazıldı.

## 16. JAR'da olup katalogda olmayan 7 kaynak (2026-11-14)

- **Yöntem**: Her siteye ayrı ajan gitti; yalnız GET/curl ile DOM sayıldı, seçici uydurulmadı. Sonuçlar `.work/tani/<domain>-secici.md`; ana oturum sayıları curl ile tekrar doğruladı.
- **Katalog kaydı eklendi (3)**: `mangakulesi.com` (liste `a.group[href*="/manga/"]` 13, bölüm `a[href*="-bolum-oku"]` 19, sayfa `div.ep-item img` 45), `mangamac.com` (liste `/mangalar` 24 kart, bölüm `a.arc-chapter-item`, sayfa `.reader-container img.reader-page`), `webtoonia.fun` (eski kayıt vardı ama seçicileri varsayılandı: liste `/seri` 10 kart, bölüm `.wtsp-chapter a.wtsp-chapter-thumb` 24, sayfa `div.reading-content img.wp-manga-chapter-img` 4; `data-src` başında boşluk var, `parsePages` `trim()` yapıyor).
- **Seçiciyle çözülmeyenler (4)**: `merlinmanga.com` bölüm listesi yalnız admin-ajax POST (`action=manga_get_chapters` → HTTP 400); `norascans.com` SPA + `/api/series/{slug}/chapter/{n}` `pages:[]` (gerçek görsel yok); `outcatscans.net` bölüm sayfası login/rol istiyor, anonimde görsel 0; `kazescans.com` Blogger/JS — liste DOM'da 0, bölümler feed JSON'unda (motor desteği gerekir).
- **Spec `list_path`**: `04_auto_generator.py` artık spec'teki `list_path` alanını `listPath` olarak alıyor (mangamac `/mangalar`, webtoonia `/seri`). Aksi halde motor varsayılanı `/manga` 404 veriyordu.
- **Durum akışı**: `repo/source_map.json` katalog bölümü 97 kayıtla tazelendi (engine listesi korunarak), `pulsar status` + `pulsar health --domain ...` ile 4 kayıt `active` oldu. `pulsar health` artık `--domain a.com,b.com` süzgeci alıyor; tüm TR'yi yeniden test etmeden tek kaynak doğrulanabiliyor.
- **Merge tuzağı**: `niverafansub.org` engine parser'ı da olduğu için merge katalog klonunu düşürüyor (`kept: NiveraFansub`); engine kaydı cihazda SSL zinciri hatasıyla `pending` olduğundan Nivera APK'da görünmüyor. Katalog klonunun yaşaması için engine'ın düşmesi/ölü işaretlenmesi gerekir.
- **Doğrulanmadı**: Üç yeni kayıt hiçbir APK'da derlenmedi ve cihazda açılmadı; seçici sayıları yalnız curl DOM sayımı. Arama üç sitede de yok (LiveCheck arama adımı koşmuyor).
