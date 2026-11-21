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

## 17. Tamir turu: merge kapısı ve seçici ölçümü (2026-11-15)

- **Kök sorun**: aynı hostta engine parser varsa `merge` katalog klonunu düşürüyordu. Motor cihazda düşmüşse (pending) kaynak tamamen kayboluyor, tamir edilmiş katalog kaydı yayına giremiyordu.
- **Yeni kapı**: `merge` artık `source-status.json` okur. Motor yayındaysa (active veya sorun işaretli) klon yine düşer; motor yayında değilse klon YALNIZ `selector_verified: true` ise kalır. Böylece ölçülmemiş varsayılan config yayına sızmaz. `--status` ile dosya değiştirilebilir, yoksa eski davranış.
- **Bu turda tamir**: `tarotscans.com` (liste `div.page-item-detail` 10, bölüm `div.chapter-item` 20, sayfa `div.page-break img` 10 data-src) ve `kencomics.com` (eski kenscans; ana sayfa 60 `figure.card-group`, bölüm `a[href*="/chapter-"]`, sayfa `img[data-reader-page-image]` 47). İkisi de `selector_verified` ve status `active`.
- **Seçiciyle çözülmeyenler** (bozuk-teshis.csv'ye siniflandi): adonisfansub/afroditscans/tuhafscans/madarascans sayfa gorselleri JS/API'de; golgebahcesi Next.js reader-stage; anikiga/gafeland chapter listesi tembel/AJAX; mangadenizi detayda 1 bolum; webtoontr/mugimanga/guncelmanga/mangawt/araznovel/asemifansub/alterkaiscans liste DOM'da yok; mangakazani/noxscans/mangatr.app JS challenge; raindropteam/piedpiper/seraphmanga bot/rate-limit; garciamanga/mangaokusana/guildknives olu.
- **SSL ayrimi**: `openssl s_client` ile zincir kontrolu. koreliscans, milascans.tr, laviniafansub.site `code 20` → Android'de onarilamaz. Kuroimanga, niverafansub, zamanmanga, summertoon, mangaoku.org, snscoeurturkey zinciri saglam → cihaz hatasi bayat olabilir, yeniden test gerekir.
- **Dogrulanmadi**: yeni iki kaynak APK'da derlenmedi/cihazda acilmadi; bu turda APK testi yapilmadi.

## 18. Tum paket cihaz raporu ve uc tamir (2026-11-15)

- **Rapor**: `kototoro-source-test-1794693078.json` (2026-11-14T21:51Z). 530 kaynak denendi: 143 gecti, 381 dustu, 6 Cloudflare. Hata listesi 387 kayit: 378 engine (JitPack parser) + 9 TR.
- **TR hatalari (9)**: Amanga Planet (pages 403), Anikiga (details admin-ajax 400), Kuroi Manga (pages PROTOCOL_ERROR), Lunar Manga (pages 404), Nyx Scans (pages bos), OpiaToon (details login sayfasi), ShadowCeviri (search bos), Tarot Scans (search bos), TilkiScans (covers/pages Cloudflare).
- **Tamir 1 - Tarot arama**: `?s=` arama sayfasi sonuc dondurmuyor; dogru uc `?s={query}&post_type=wp-manga`, sonuclar `div.c-tabs-item__content` icinde. `searchUrl` eklendi, `itemSelector` birlestirildi. Curl: arama 10 kart, liste 12 kart.
- **Tamir 2 - Nyx sayfa**: script (`data-tsr-stream-part`) sayfa listesi bos donuyordu; sayfalar duz `<img src=".../page-0001...">`. `readerSelector: img[src*="/page-"]` eklendi. Curl: reader 200, 66 gorsel.
- **Tamir 3 - Lunar liste**: liste JS ile geliyor, HTML'de gercek manga bagi yok; `genericList` `/manga/search` bagini manga sanip 404 uretiyordu. `listJsonUrl=api.lunarx.to/api/manga/search?query=&page={page}`, `listJsonItems=manga`, `listJsonUrlTemplate=/manga/{slug}`, `listJsonCover=cover_url` eklendi. Curl: s1 30 (the-cliff), s2 30 (melting-slowly), bolum API 15 gorsel.
- **Cozulemeyenler**: Amanga `amip-proxy` referer/cerez/UA ile de 403; OpiaToon uye girisi istiyor; Kuroi sayfa isteginde stream reset; Anikiga engine parser admin-ajax 400; ShadowCeviri engine aramayi desteklemiyor; TilkiScans Cloudflare.
- **Global/Turkce denetimi**: global paketlerde `lang=tr` kayit 0. Tek domain ortusmesi Nyx Scans: globalde Ingilizce engine parser, TR'de Turkce katalog kaydi; TR tarafinda eksik yok.
- **Dogrulanmadi**: bu uc config degisikligi APK'da derlenmedi, cihazda test edilmedi. Telefona adb ile erisim yok; rapor dosyasi analiz edildi.

## 19. Desen kataloğu: belirti → tamir (2026-11-16)

240 cihaz hatasının tek tek `curl` ile ölçülmesinden çıkan tekrar eden desenler. Yeni bir kaynak düşünce önce buradaki belirtiye bakılır; her satır en az bir kez canlı ölçümle doğrulandı.

| Belirti (cihaz/rapor) | Gerçek sebep | Tamir |
|---|---|---|
| `TANI ... sel=0 gen=0` (detayda 0 eşleşme) | `config` içinde `.__yok__` yer tutucusu, ya da ayarlar üst düzeyde | Yer tutucuyu sil (boş = motorun genel seçicisi); alanları `config` altına taşı |
| `Kapak URL yok` | `parseList` dar zincir kullanıyordu (`data-src`/`src`) | Artık `coverOf`: `data-original`, `data-lzl-src`, `data-cc-src`, `data-default-src`, `srcset`, `data-bg`, `background-image`, 4 üst öğe |
| `Sayfa listesi boş`, HTML'de `<img>` yok | Madara bölümleri `POST {detay}ajax/chapters/?t=1` HTML parçası | `chapterAjaxUrl: "{url}ajax/chapters/?t=1"` (motor desteği 1.6.119+) |
| Bölüm sayfası 403 `Cf-Mitigated: challenge` | Cloudflare HTML'i kapatıyor, API açık | HTML'i bırak, JSON API'ye geç (§20) |
| `?s=` arama 0 sonuç | WordPress araması `post_type` istiyor | `searchUrl: "https://site/?s={query}&post_type=wp-manga"` (mangazin) |
| Arama sayfası SPA kabuğu (258 KB, 2 link) | Next.js/Vue; HTML'de sonuç yok | `searchUrl: ".../api/search?q={query}"` + `searchJsonItems/Url/Title/PathPrefix` (elftoon) |
| POST arama gerekiyor | Madara `admin-ajax.php` | `searchMethod: "POST"`, `searchBody: "action=wp-manga-search-manga&title={query}"`, `searchJsonItems: "data"` (tilkiscans) |
| `HTTP 404` ama site 200 | Eski URL kalıbı / yanlış slug | Gerçek detay linkini ana sayfadan al; `listPath` + `itemSelector` düzelt (7/11 vaka) |
| `Connection reset` | Site ölü değil (34/41 PC'den 200) | Domain taşınması ve CDN/IPv6 ara; UA zaten Chrome/124 gönderiliyor |
| `Zaman aşımı (20s)` | Çoğunlukla CF challenge veya 301 zinciri | CF ise `failed` bırak; 301 ise `baseUrl` güncelle |
| Ana sayfa 200, `/manga/` 404 | Site yalnız ana sayfayı servis ediyor | Ölü işaretle (kalango.org) |
| Domain park sayfası | `parklogic`, `sedo`, `bodis`, "Buy this domain", "Account Suspended" | `status: "dead"` + gerekçe (laviniafansub, cococomic) |
| Site el değiştirmiş (başka dil/tür) | Domain satılmış | Ölü işaretle (speed-manga.com, lunarx.to) |
| Vue/Next SPA, `/api/...` var | HTML'de liste yok, JSON var | `listJsonUrl` + `listJsonItems` + `listJsonUrlTemplate` + `listJsonCover` (stonescape) |

**Ayrım kuralı**: "liste boş" üç ayrı hastalıktır ve tedavisi farklıdır — (a) `listPath` yanlış, (b) kart seçicisi 0 eşleşiyor, (c) sayfa JS ile doluyor. Üçünü ayırmadan config yazmak boşa gider; önce `grep -c` ile kart sayısı ölçülür.

**Ölçüm tuzağı**: HTML tek satırsa `grep -c` her zaman `1` döner. Kapak grubunde 52 kaynağın 29'u "kart 0 eşleşiyor" sanıldı; doğrusu `grep -o ... | wc -l`. "Kapak URL yok" hatası da çoğu zaman kapak değil **liste seçicisinin hiç eşleşmemesi**dir: kartı bulunan 23 kaynağın 21'inde kapak düzeltmesi çalıştı (%91).

## 20. OkuToon vakası: CF'li HTML'i bırak, JSON'u al (2026-11-16)

- **Belirti**: cihazda `pages` adımı 20 sn timeout; bölüm sayfası 403 `Cf-Mitigated: challenge` + `<title>Just a moment...</title>`. Liste ve detay 1 sn altında.
- **Yanlış yol**: UA, Referer, HTTP/1.1 denemeleri — hepsi 403. Bu Cloudflare aşılabilir değil.
- **Doğru yol**: site kendi okuyucusunu besleyen JSON ucunu açık bırakıyor:
  `GET https://okutoon.com/api/v1/series/{slug}/chapters/{bolum}` → 200, `data.pages[].image_url`; görseller `cdn.okutoon.com` üzerinde ve başlık istemiyor.
- **Config**: `pageApiUrl` (`{1}`,`{2}` yakalama grupları) + `pageApiIdPattern` + `pageApiItems: "data.pages"` (noktalı yol) + `pageApiFieldUrl: "image_url"`.
- **Genel ders**: HTML 403 alan her sitede önce `grep -oE '"/api/[^"]*"'` ile uç aranır. Okuyucu görselleri çoğu sitede ayrı CDN'de ve CF koruması yok.

## 21. Yerel test hattının gerçekleri (2026-11-16)

- `pulsar sweep --apk ... --engine` **yalnız motor parser'larını** test eder (test APK'sında 9 kaynak); katalog (custom) kaynaklar listeye hiç girmez. CSV'deki `id` alanı her zaman sayısal hash'tir; metin id beklemek yanıltır.
- `PulsarData.kt` **üretilen** dosyadır: `tools/pulsar/src/embed.rs` şablonundan yazılır. Kalıcı düzeltme şablona yapılır, yoksa bir sonraki `embed` ezer.
- Masaüstünde `android.util.Base64` "bad base-64" atıyordu; `decode` artık boşluk temizleyip `java.util.Base64.getMimeDecoder()`'a düşüyor. Harness'ın katalog kaynaklarını görebilmesi için gerekliydi.
- Kototoro masaüstü jar'larında `SourceFactory`/`MihonSourceRuntime` var; `javac` PrismLauncher runtime'ında. Yerel Mihon harness'ı bu ikisiyle kurulur (`tools/harness/`).
- Test edilemeyen kaynak "temiz" sayılmaz: `pulsar status` içinde `unknown`/`pending` kalan her kayıt açık iştir.

## 22. Yayın sayıları nasıl okunur (2026-11-16)

- `catalogue.json` = bizim kayıtlarımız (553). `assets/catalogue.json` = `merge` sonrası yayına giren küme (437). `index.min.json` = paketlerdeki gerçek kaynak toplamı (478).
- 478 > 437 çünkü paketler motor kaynaklarını da taşır; fark arıza değildir.
- `pulsar embed` sayısı ile yayın indeksi ayrı şeylerdir: indeks `deadSources`/`deadHosts` ve `generate_repo.py` kapılarından geçer. Fark çıkınca `patches.json` içindeki listelere bakılır.
- Elle `assets/patches.json` düzeltmesi kalıcı değildir; `06_prepare_assets.py` onu yeniden üretir.

## 23. `source-status.json` kimlik kuralı (2026-11-17)

- Anahtarlar **sayısaldır**: `pulsar_id("pulsar/<domain>/<lang>")` hash'i (`tools/pulsar/src/merge.rs:145`, Kotlin `PulsarSource.kt:78`). String anahtar (`"tilkiscans.com"`) yazmak hiçbir kaynağı açmaz; fabrika beyaz listesi `it.id.toString() in allowed` ile karşılaştırır (`PulsarSourceFactory.kt:101`).
- `pulsar status` çalışınca `source_map.json` id'lerini `retain` eder; haritada olmayan yeni bir giriş bir sonraki koşuda düşer. Kalıcı çözüm `emit_source_map.py` ile haritayı yenilemektir (CI yapar).
- **Node tuzağı:** id'ler 2^53'ü aşan i64. `JSON.parse` + `JSON.stringify` bu değerleri yuvarlar (`7849977061084682679 → ...680`), yani dosyanın tamamı bozulur. Bu dosyayı düzenleyen araç int'i koruyan bir okuyucu kullanmalı (Rust `i64` veya Python `int`).
- Aynı domainde hem eski `kind:"engine"` hem yeni `kind:"catalogue"` kaydı varsa, domain üzerinden eşleştirme yapan her işlem **yanlış kayda** gider. Bitişik kayıtlar için önce `kind` filtresi uygulanır.

## 24. Kanıtlanmış çözülemezler (2026-11-17)

Bu üç kaynak API avıyla **ölçülerek** kapandı; tekrar denenmesi gereksiz:

| Kaynak | Neden çözülemez |
|---|---|
| `pocket.shonenmagazine.com` | Uç var (`GET /episode/viewer?episode_id=`), ama her istek params'tan hesaplanan `requestHeaderServiceHash` + `x-app-assertion` başlığı istiyor; imza istemcide üretiliyor. Config ile üretilemez. |
| `lectorhentai.com` | Okuyucu `reader-blob.js` (javascript-obfuscator) ile AES-GCM çözüyor; `ts_reader` içindeki 24 URL placeholder SVG, `data-rb` öğesi sayfada 0. Bölüm listesi CSRF'li `POST get_chapters`. |
| `piccoma.com` | Coğrafi blok: ürün/okuyucu sayfası "bu hizmet yalnızca Japonya'da kullanılabilir" döndürüyor. Ana sayfa açık, ürün sayfası kapalı. |

Kural: bir kaynak için "JS" teşhisi konduğunda **önce API ucu aranır** (en fazla 3 uç); uç varsa imza/CSRF/geo kontrolü yapılır. Bu üçünde kapanış nedenleri yukarıdaki gibidir; `failed` kalırlar.

## 25. Bu oturumun dersleri (2026-11-17)

- **Motorun varsayılan liste yolu `/manga`.** `popularMangaRequest` içinde `config.optString("listPath", "/manga")` (`PulsarSource.kt:104`). Ana sayfası `/` olan sitede config'e `listPath: "/"` yazılmazsa istek `/manga`ya gider ve liste boş döner. "Liste boş" teşhisinde ilk bakılacak alan `listPath`tir.
- **`itemSelector` doğrudan `<img>` seçmemeli.** `parseList` her öğede `a[href]` arar (`EngineRegistry.kt:224-225`); `<img>` öğesinin altında bağlantı olmadığı için kart üretilemez, motor `genericList`e düşer. Gözlenen sonuç: kapak (bazı kaynaklarda liste) boş. Seçiciyi kart kapsayıcısına (`div.rec-item`, `div.page-listing-item` vb.) çevirmek ikisini birlikte düzeltir; katalog geçmişinde `img` seçicileri bu şekilde kapsayıcıya çevrildi (ör. `fa8c5cd`).
- **`sorun` etiketi cihaz sonucunu ezmemeli.** `status.rs` cihaz testi `pass` ise elle işaretli `sorun`'u uygulamıyor ve önceki turdan kalan etiketi temizliyor (`status.rs:251-256`, `2fd9ca5`). Slept Manga dört adımı da geçtiği halde `sorun:"cloudflare"` yüzünden test paketinde kalıyordu. Sağlık `ok` tek başına `state=active` yapar (`status.rs:164`) ama etiketi silmez; bu durumda kaynak `sorun` dolu olduğu için yine test havuzuna düşer (`status.rs:102`).
- **`kapali` = karantina üyeliği.** `deadSources` (motor adı) veya `deadHosts` (katalog alan adı) içinde olmak `kapali` yapar (`status.rs:258-262`); böyle bir kaynak hiçbir pakete girmez (`status.rs:91`). Bayat ölü listesi canlı kaynağı test havuzundan tamamen düşürür. Canlılık ölçümü kaynağı `overrides.json` içinde `revivedSources`/`revivedHosts`'a ekler (`07_maintain.py:591-599`), `06_prepare_assets.py:127-128` bu adları `dead*` kümelerinden çıkarır.
- **CI ağı ile cihaz ağı farklı.** Sağlık ölçümü GitHub sunucusundan yapılır; Türk siteleri GitHub IP'sini engelleyebilir (`status.rs:94-98`). Bu yüzden `unreachable` kaynak ana pakete sokulmaz, test havuzunda kalır (`status.rs:99-100`); bayrak ölçüm ortamının erişimini anlatır, kaynağın ölü olduğunu değil.
- **Harness kapsamı.** Paket allowlist'i dışındaki katalog kaynakları `KAPSAM_DISI` döner (`.work/harness-tekrar.csv`). Bu kaynaklar `HARNESS_KATALOG=1` ile katalogdan doğrudan `PulsarSource` olarak örneklenip test edilir (`tools/harness/Harness.java:117-121, 285`).
- **`source-status.json` okuma tuzağı.** Dosya UTF-8'dir; okuyucuya kodlama sabit verilmezse Windows locale'i (cp1254) Türkçe alanları bozar. Node `JSON.parse` id'leri 2^53 üstünde yuvarladığı için bu dosya int'i koruyan okuyucuyla işlenmeli (bkz. §23).
- **`PulsarData.kt` üretilen dosyadır.** Kalıcı düzeltme `tools/pulsar/src/embed.rs` şablonuna yazılır; doğrudan Kotlin dosyası bir sonraki `embed` koşusunda ezilir (bkz. §21).

## 26. Yanlış etiket kaynağı öldürür (OkuToon dersi)

- OkuToon'a ilk turda **"Cloudflare"** dendi: bölüm HTML'i gerçekten `403 Cf-Mitigated: challenge` dönüyordu. Bu, kaynağın ölü olduğu sanısına yol açtı.
- Gerçek durum: HTML kapalıydı ama site kendi okuyucusunu besleyen **JSON API'yi açık bırakıyordu** — `GET /api/v1/series/<slug>/chapters/<bolum>` → `data.pages[].image_url`, görseller `cdn.okutoon.net`. Aynı desen Gölge Bahçesi'nde `api.<site>/api/chapters/.../manifest` olarak çıktı.
- İkinci yanlış: "JS_RENDER" etiketi. JS, "veri HTML'de yok" demektir; "veri yok" demek değildir. JS etiketli 45 kaynağın bir kısmı (MangaKatana `thzq=[...]`, Tapas `img.content__img`, Nikkangecchan `img.episode-page`) tek bir uç/attribute bulunduğunda açıldı.
- Kural: `Cloudflare` ve `JS_RENDER` **ara karardır**. `failed` yazmadan önce (a) JSON ucu, (b) script içi JSON, (c) bilinen CMS uçları denenir; sonuç yoksa karar nedeni yazılır (`IMZA_GEREKLI`, `CSRF_GEREKLI`, `GEO_BLOK`).
- Doğrulanmış imkânsızlar: `pocket.shonenmagazine` (imza), `lectorhentai` (AES-GCM + CSRF), `piccoma` (Japonya IP bloğu).

## 27. Cloudflare ve çerez yolu (2026-11-18)

- Motor artık kaynak `config` içinde iki alan okuyor: `cookie` (ham çerez dizesi) ve `userAgent`. `cookie` doluysa `headersBuilder()` sonunda `Cookie` başlığı yazılır; `headers` nesnesinde `Cookie` varsa o kazanır ve `config.cookie` uygulanmaz.
- Çerez tarayıcıdan alınır: siteyi aç, DevTools → Application → Cookies → site adı; `cf_clearance` ve `__cf_bm` satırlarındaki değerleri kopyala. `cookie` alanına `cf_clearance=...; __cf_bm=...` biçiminde tek satır yazılır (JSON içinde normal string; kaçış gerekmez, `;` ve boşluklar korunur).
- `cf_clearance` tarayıcının **User-Agent**'ına bağlıdır: `userAgent` alanı çerezi aldığın tarayıcının UA'sıyla birebir aynı olmalı, yoksa 403 sürer. `userAgent` boşsa motorun varsayılan masaüstü UA'sı kullanılır.
- Çerez **IP'ye bağlıdır**: wifi → mobil veri gibi ağ değişiminde geçersizleşir; çerez, tarayıcının o anki IP'siyle alınmalı.
- Ömür kısadır: `__cf_bm` yaklaşık 30 dakika, `cf_clearance` birkaç saat — **siteye göre değişir**. 403 geri dönerse ilk iş çerezi tarayıcıdan yeniden almaktır.
- Çerez çözüm değil köprüdür: kalıcı çözüm hâlâ JSON ucu/API aramaktır (§20, §26). Çerezli kayıt cihaz testinde `pass` alsa da çerez bayatlayınca düşer; bu yüzden çerezle açılan kaynakta `sorun` alanına `cloudflare:cerez` notu düşülür.

## 28. Motor ve defter kusurları: belirti → kök neden (2026-11-18)

Bu turda düzeltilen kusurlar; her biri gerçek cihaz/harness hatasıyla tetiklendi. Yeni bir hata görüldüğünde önce bu listeye bakılır.

- **`searchUrl` göreli yazılınca arama patlıyordu.** `/?s={query}` gibi değer `Request`e düz verildiğinde `IllegalArgumentException: Expected URL scheme 'http' or 'https'`. Düzeltme: `absolute()` yardımcısı göreli yolu `baseUrl` ile birleştiriyor; `searchUrl`, `listJsonUrl`, `chapterApiUrl`, `pageApiUrl`, `pageApiLookupUrl`, `chapterAjaxUrl` bu yoldan geçiyor (`ce45410`). Belirti cihazda "search fail" — site sağlamdır.
- **Bölüm listesi boşken istisna atmak kaynağı komple düşürüyordu.** `chapterListParse` `chapters.isEmpty()` durumunda `IllegalStateException` atıyordu; cihaz testi listenin **ilk** serisini seçtiği için 0 bölümlü seri (OkuToon `/personant`) kaynağı `list=0` gösteriyordu. Düzeltme: `return emptyList()` (`39f6c10`). Kural: bölümü olmayan seri Mihon'da boş liste döndürür, hata değildir.
- **`pageApiIdPattern` host içeriyorsa desen hiç eşleşmez.** Motor deseni relativize edilmiş bölüm yoluna uyguluyor (`/absolute-dominion/bolum-116`), `okutoon\.com/...` gibi host'lu desen asla eşleşmez ve sayfa API hiç çağrılmaz. Kural: desende host olmaz; `(d+)` yazımı da sessiz hatadır, `(\d+)` olmalı (`4601bc8`).
- **`www.` kimlik uyuşmazlığı kaynağı görünmez yapar.** `PulsarSource.id` ham `domain`den üretiliyordu, `source_map`/`source-status` ise `www`'siz host'tan. Sonuç: `www.` ile başlayan kayıt izin listesinde bulunmaz, kullanıcı kaynağı hiç görmez. Düzeltme: id hesabında `domain.removePrefix("www.")` (`07d5c78`); katalog tarafında `domain` alanından `www` kaldırıldı, `baseUrl` korundu.
- **`kapali` kayıt paket listesinde kalabiliyordu.** `recompute_state` yalnız `dead` için erken dönüş yapıyordu; `active` + `kapali` kayıt `packages=["global18"]` alıp APK izin listesinde hayalet id bırakıyordu. Düzeltme: `kapali` da `state="dead"`, `packages=[]` (`32d5c68`).
- **`dead` ve `reason` her `status` koşusunda siliniyordu.** `ensure_all` `dead` alanını katalogdan yeniden hesaplıyor, `StatusEntry` struct'ında `reason` alanı hiç yoktu. Düzeltme: `s.dead = s.dead || ...`, `reason` alanı eklendi, katalog `reason`'ı deftere taşınıyor (`6b61985`, `b9d99fd`).
- **Cloudflare = "ölçemedik", "kırık" değil.** Bu yüzden ayrı durum: `engelli`. `sorun=="cloudflare"` veya `reason` `CF:` ile başlıyorsa `state="engelli"`, `packages=[]`; ne yayınlanır ne test edilir. Kalıcılık `reason` metnine bırakılmaz: `ensure_all` `sorun` boşken `reason`'dan `cloudflare` türetir (`49d9cc0`, `764f271`).
- **Harness listenin ilk serisine takılmamalı.** İlk kart 0 bölümlüyse kaynak haksız yere "bölüm listesi boş" düşüyordu. Düzeltme: en fazla 6 seri ve 3 bölüm denenir (`Harness.java`). Cihaz testi de aynı tuzağa düşer; cihazda `chapters: Bölüm listesi boş` görülürse önce seçilen serinin bölümü var mı bakılır.
- **Cihaz raporu `MIHON_<id>` taşır; id = pulsar_id.** Rapordaki bir kaynağın hangi katmanda (katalog/motor) ve hangi durumda olduğu `source-status.json` anahtarıyla birebir eşleşir. "Bu hata yayında mı?" sorusu tahminle değil bu eşleştirmeyle yanıtlanır (§23).
- **Canlılık taraması DNS önbelleğine kanabilir.** Aynı domain bir turda `CANLI`, ertesi tur `ENOTFOUND` çıkabiliyor; `CANLI` kararı tam ölçümle doğrulanmadan `active` yapılmaz.
- **`reason` aktarımı `dead` bloğuna bağlıydı → engelli kayıtların gerekçesi kayboluyordu → aktarım `dead` koşulundan çıkarıldı.**
- **Bayat `reason` katalogdan geri gelir.** `pulsar status`, defterde silinen `reason`'ı `catalogue.json`'daki değerden yeniden yazar; promote sonrası etiketin gitmesi için **kaynak** alan (`catalogue.json`) temizlenir. Aynı mantık `sorun` için de geçerlidir.

## 29. Paket denetimi dersleri (2026-11-19)

tr18 ve test paketi denetimlerinden (ölçümlü) çıkan dersler; aynı desen yeni kaynakta görülünce önce buraya bakılır.

- **Madara üye kilidi = ENGEL.** Bölüm HTML'inde `div.reading-content` içinde `content-blocked login-required` ve "Bu seriyi okumak için siteye üye olmalısınız" varsa sayfa listesi üretilemez; UA/Referer/çerez denemesi sonucu değiştirmedi (averis, kuroimanga; iki farklı seride de aynı).
- **Madara aramasında POST + `searchBody=title={query}` + `searchJsonItems=data` yanlış.** Site HTML döndürüyor, JSON ayrıştırıcı boş liste üretiyor. Doğrusu: `searchMethod=GET`, `searchUrl=<host>/?s={query}&post_type=wp-manga`, `searchJson*` alanlarını sil.
- **Blogger/ZeistManga liste ve bölümleri JS ile feed'den gelir.** `/p/manga-list.html` ve `/search/label/Seriler` içinde seri kartı 0; `feed.entry` iç içe ve etiket manga URL'inde yok, bu yüzden mevcut `listJsonItems`/`chapterApiItems` ile tüketilemez → JS_RENDER.
- **Noktalı JSON yolu motorun dışında kalır.** Nuxt araması `hits[].document.slug` döndürüyor; motor `searchJsonUrl` alanını düz okuyor, `document.slug` yolunu çözemiyor. API 200 olsa da çalışan arama config'e yazılamaz (mangtto).
- **Madara `chapterAjaxUrl` statik detayla aynı bölümleri veriyor** (averis 22/22, kuroimanga 28). Zararsız; kaldırmak zorunlu değil.
- **Aynı Madara kurulumunun iki alan adı ayrı ayrı denenmez.** `kuroimanga.site` ile `www.kuroimanga.com` aynı tema/üye kilidi; ikisi de ENGEL, config denemesi sonucu değiştirmiyor.
- **JS/JWT kapısı ölçüm yapılamaz demektir.** `window.location.replace(ch=1&js=...)`, `_guard/html.js` (456) veya ~480B "Loading" gövdesi dönen sitelerde HTML'de içerik yok; test paketinde bu desen birden çok kaynakta aynı sonucu verdi.
- **SPA kabuğunda canlılık 200 parser durumu değildir.** Vite/SvelteKit/Vue kabuğu 5000B altında ve kart yok; ana sayfa 200 dönse de liste/ölçüm yok (DIGER: "sunucudan içerik gelmiyor").
- **Cloudflare Turnstile/challenge ölçüm değil engeldir.** `Cf-Mitigated: challenge`, `challenges.cloudflare.com/turnstile` veya "Just a moment" → `sorun=cloudflare` + `reason="CF: ..."`; kayıt `engelli` olur, ne yayınlanır ne test edilir.
- **Ana sayfada üye girişi de ENGEL'dir.** Başlık "Giriş Gerekli", form `wp-login.php` ise public içerik yok; parser ölçümü yapılamaz.

## 30. Paket denetimi, okuyucu zinciri ve iki NSFW sistemi (2026-11-19)

- **Paket denetiminde harness APK'sı eşleşmeli.** `run.sh` varsayılan olarak **test APK**'sıyla koşar; `tr`/`global`/`global18` kaynakları o APK'da olmadığı için hepsi `KAPSAM_DISI` döner. Doğrusu: `APK=pulsar-v2/repo/apk/eu.kanade.tachiyomi.extension.all.pulsar.<paket>.apk` + paket başına ayrı `EXTENSION_JAR` (JAR önbelleği paket adına bağlı).
- **Sayfalar ayrı HTML belgesi olabilir.** niadd'de bölüm sayfası tek görsel + "1 of N" + `next_page=...-2.html` taşıyor; JSON uç yok. Çözüm: `pageNextSelector` + `pageNextLimit` (varsayılan 30). Kritik: **son sayfada "Next" bir sonraki bölüme gider**; dizin (`pageDir`) koruması + ziyaret kümesi olmadan 122 fazla istek atılır.
- **Bölüm listesi `<option>` içinde olabilir.** niadd varyantlarında detay sayfasında bölüm bağlantısı yok; gerçek liste okuyucu sayfasında ve `<option value="/chapter/...">` olarak duruyor. Detaydan beslenen `chapterSelector` bu yüzden 1 bölüm bulur. Çözüm: `chapterAjaxUrl={url}/chapters.html` + `a.hover-underline[href*="/chapter/"]`.
- **Bayat `deadHosts` kaynağı görünmez yapar.** `ruhmanga.com` kaydının `altDomains`'inde `mangaruhu.com` vardı; o host `patches.json` deadHosts'ta olduğu için fabrika kaynağı eliyor, harness aynı adlı `@Broken` motor kaynağını seçip `UnsupportedOperationException` veriyordu. Düzeltme: `maintenance/overrides.json` deadHosts → revivedHosts.
- **Cloudflare iki ayrı sistemdir.** (1) **Paket bayrağı** APK manifestinden okunur: `tachiyomix.contentWarning == 2` ya da `tachiyomi.extension.nsfw == 1` → paketin tamamı 18+. Bu bayrak yoksa 18+ paket eklenti yönetiminde yetişkin görünmez. (2) **Kaynak etiketi** Mihon modelinde kaynak başına yoktur (`ExtensionSourceDto` yalnız name/id/lang); kaynağı 18+ paketine koymak tek yoldur, tek tek işaretleme kullanıcı tarafındadır (`SourceNsfwOverrides`).
- **CF'li sitede önbellekli ana sayfa canlılık kanıtı değildir.** `cocomic.co`: ana sayfa 200 ama detay 502, bölüm 60 sn'de 0 bayt → site ölü.
- **İki build aynı anda tetiklenirse APK commit'i çakışır.** "Commit and push artifacts" adımı binary çakışmasıyla düşer; derleme geçse de yayın yenilenmez. Tek build tetikle, bitmesini bekle.

## 31. URL normalizasyonu, sahte bölümler ve ölçüm tuzakları (2026-11-20/21)

- **Göreli→mutlak dönüşüm tek noktadan geçmeli.** Ayrı ayrı `"$baseUrl/${raw.trimStart('/')}"` birleştirmeleri `//host/path` (protokol-göreli) adreste `https://host/host/path` üretiyordu → 404. `EngineRegistry.absoluteUrl()` (44a7ae1) tek nokta oldu; `//` → `https:`. Aynı commit'te: bölüm JSON'unda `\/` kaçışı çözüldü (bacakomik 0→6 sayfa), sayfa zincirine `data-lazy` eklendi, `rawImages` göreli yolu yakalıyor, kök JSON **dizisi** cevapları okunuyor. Kontrol kümesi 8/8 sabit kaldı.
- **Bölüm sezgiseli yabancı hostu bölüm sanıyor.** `genericChapters` `blogger.com/share-post`, `facebook.com/...`, `t.me`, `x.com` gibi bağlantıları bölüm sayıyordu → `pages=0`. 3a34308 aynı kayıtlı alan adı + promo host filtresi ekledi (idol 0→13, mangaplexe 0→2 sayfa). Filtre "kendi sitesi" kontrolünden SONRA çalışır: repoda 546 `*.blogspot.com` kaynağı var, promo listesi önce uygulansaydı onların kendi bölümleri de elenirdi.
- **Galeride CDN görsel bağlantısı da "bölüm" olur.** Tam boy görseller `<a href=".../001.jpg">` ise `genericChapters` onları bölüm sayıyor, `singleChapter` hiç tetiklenmiyor. Config yolu: `chapterApiUrl="{url}"` (ve gerekiyorsa `chapterApiIdPattern`) dolu bırakılır, `apiChapters` HTML'de boş döner, tek bölüm yolu devreye girer. Kalıcı çözüm motora "bölüm listesi kapalı" anahtarı eklemektir; 6 kaynak (pmatehunter, pornsticky, pawchive, ilikecomix, idol, mangaplexe) bu hileyle düzeldi.
- **`failed` havuzu gerçekten ölü.** Motor düzeltmelerinden sonra 50 kaynaklık örneklem (8 eski `OnNextValue`, 9 "bölüm listesi boş", 33 "liste boş") yeniden koştu: **0/50 geçti**. Bu havuzu topluca yeniden test etmek boşa build döngüsü; yalnız tek tek ölçümle karar ver.
- **Harness paralel koşmaz.** Dört süreç ayrı `HARNESS_CLASSES` ile başlatılsa bile Kototoro tercih deposu ortak: 24 kaynak `IOException: Preference directory already exists` verdi (kaynak hatası değil). Seri koş; `HARNESS_CLASSES` yalnız sınıf dizini çakışmasını çözer.
- **Terfi `at` alanı olmadan yazılamaz.** `Probe.at` zorunlu; eksikse deserializasyon `.ok()` ile yutulur ve defter boşalır. `steps` şemada **yok**, pipeline sonrası düşer — kalıcı tutmak istiyorsan `status` sonrası geri yaz ya da şemaya ekle.
- **`06_prepare_assets.py` çıktısındaki `total_count` bayat.** "N kaynak" satırı `data/catalogue.json`'daki eski alandan geliyor; asset'in gerçekten büyüdüğünü `extension/src/main/assets/catalogue.json` dosyasını ayrıca sayarak doğrula.
- **A/B için APK'yı sabitle.** Paralel CI derlemeleri `repo/apk/*.apk` üzerine yazıyor (versionCode 248→249→250); önce/sonra karşılaştırması yaparken APK'nın bir kopyasını `.work/` altına al, yoksa "önce" ölçümü de yeni kodu koşar.
- **Galeri detayı önizleme görseli taşıyabilir.** 250×176 thumbnail'ı `singleChapter` ile okutmak düşük çözünürlük üretir; tam boy `/view/<id>/N/`, `/g/<id>/N/`, `/galeria?id=` gibi izleyici sayfalarındaysa onları `chapterSelector` yapıp `readerSelector`'ı izleyiciye yaz.
- **Liste kartı seçicisi kartın tamamı değil gerçek bağ olmalı.** `div.thumbnail` gibi kapsayıcıda ilk `<a>` dil/etiket linki olabiliyor (imhentai `div.thumb div.inner_thumb`), ya da ilk kart bir reklam/duyuru olabiliyor (hentaifusion `t.me`, comics18 metin ilanı → harness hep o kartta kalıp `pages=0` veriyordu).

## 32. Ağ engelleri, Aniyomi depo sözleşmesi ve tarama tuzakları (2026-11-21)

- **Ağ engeli iki katmanlı: DNS ve SNI.** Türkiye ISP'sinde önce DNS (UnknownHost → 301 kaynak), DNS açılınca TLS el sıkışması sıfırlanıyor (`SocketException: Connection reset` → 95 kaynak). `curl` ile ayrımı yap: `000` + `curl: (35)` = TLS, `Could not resolve` = DNS.
- **DoH tek başına yetmez.** `dnsOverHttps` 301 kaynağı 0'dan 192'ye çıkardı; kalan 95 için `tlsFragment` gerekti (95 → 94). İkisi ayrı katman, biri diğerinin yerine geçmiyor.
- **Motorda otomatik yedekler artık var:** `DohFallbackDns` (sistem DNS düşerse DoH) ve `TlsRetryInterceptor` (`X-Pulsar-Tls-Retry` başlığıyla parçalı ClientHello ile tek tekrar). `tlsFragment`/`dnsOverHttps` config'i artık zorunlu değil; `dnsOverHttps:"off"` yedeği kapatır.
- **Kototoro depo eklerken önce `repo.json` ister.** `ExtensionRepoService.kt:182-201`: `{index_v2, meta:{name, website, signingKeyFingerprint}}`; parse olmazsa `index.pb`'ye düşer ve 404 verir. `index.min.json`'ın kök dizi olması yetmez, `repo.json` da doğru biçimde olmalı.
- **Aniyomi eklentisinde `versionName = <lib>.<yama>`'dır.** Kototoro lib sürümünü `versionName.substringBefore('.')` ile okur, aralık **12–16** (`AniyomiExtensionLoader.kt:53-54,229`); `1.0.2` yazarsan "kütüphane sürümü desteklenmiyor" hatası alırsın. Doğrusu `16.1`, `16.2`…
- **Depo indeksinde `sources` boşsa "0 etkin kaynak" görünür.** Kototoro kaynak sayısını indeksten okur (`ExtensionRepoService.kt:372-410`); `pulsar video-repo` bu alanı katalogdan üretir.
- **Harness paralel koşarken `HARNESS_ROOT` şart.** `FileSourcePreferenceStore` tercih dizinine `.owner.lock` koyuyor; aynı kökte iki JVM `Preference directory already has an owner` veriyor. `HARNESS_CLASSES` tek başına yetmez.
- **`KATALOG_DISI` her zaman "kaynak yok" demek değil.** Motor kaynakları (`PulsarKotatsuSource`) `domain=null`, `baseUrl=""`, id'si `pulsar-kotatsu/<AD>/<dil>` hash'i; harness domain ile eşleştirdiği için bulamıyor. `HARNESS_DUMP=1` ile paket başına örnek sayısını dök (TR 48/48, GLOBAL 245/245) — silmeye kalkmadan önce bunu kontrol et.
- **Ölçüm makinesindeki DPI aracı sonucu değiştirir.** GoodbyeDPI `-1` açıkken (SNI bölme + sahte paket) yerel testler telefondan iyi çıkar; bu yüzden APK içi otomatik DoH/TLS yedeği asıl çözümdür, yerel yeşil sonuç kullanıcıyı temsil etmez.
- **Sayfa tipi kapısı 200 + `text/html` ile sınırlı olmalı.** CDN'ler hotlink korumasında referersız isteğe `403 text/html` döner (2xstorage: referersız 403, refererli 200 webp); 403'ü reddetmek çalışan kaynağı haksız düşürür.
