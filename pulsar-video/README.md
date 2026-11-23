# pulsar-video — video (anime) kaynak paketi

Manga paketlerinden bağımsız, **Aniyomi formatında** ayrı bir eklenti. Kototoro ve Aniyomi,
`tachiyomi.animeextension` feature'ı olan APK'ları yükler
(`AniyomiExtensionLoader.kt`: feature `tachiyomi.animeextension`, anahtarlar `.class`, `.factory`, `.nsfw`).
Aynı kod tabanı iki pakete ayrılır: **Pulsar Video** (normal) ve **Pulsar Video 18+** (hentai).
Fabrika parser kaynaklarını `ContentType` alanına göre süzer; config tabanlı kaynaklar (GogoAnime,
AniWorld) iki pakette de bulunur.

## Kurulum (Kototoro / Aniyomi)

Depo adresi (klasör ya da `index.min.json`, ikisi de çalışır):

```
https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/pulsar-video/repo
```

Kototoro → Ayarlar → Kaynaklar → Depo ekle → bu adresi yapıştır.

Depoda iki dosya var:

- `repo.json` — metadata; Kototoro depo eklerken **önce** bunu çeker ve
  `{index_v2, meta:{name, shortName, website, signingKeyFingerprint}}` şemasını arar
  (`ExtensionRepoService.kt:182-201`). Yanlış biçimde 404/`index.pb` yoluna düşer.
- `index.min.json` — eklenti dizisi (`name, pkg, apk, lang, code, version, nsfw, sources[]`), **iki kayıt**.
  `sources` alanı `data/video-sources.json`'daki parser adlarından (`video` / `hentai_video`) ve
  `data/video-catalogue.json`'daki config'i dolu kayıtlardan üretilir; boş kalırsa Kototoro
  "0 kaynak" gösterir ve kuruluma geçmez.

Sürüm kuralı: `versionName = <lib>.<yama>`. Kototoro lib aralığı **12–16**
(`AniyomiExtensionLoader.LIB_VERSION_MIN/MAX`; sürümü `versionName.substringBefore('.')` ile okur),
bu yüzden sürümler `16.x`. `versionCode` her yayında artmalı — aksi hâlde kurulu kullanıcı güncelleme görmez.

Üretim: `pulsar video-repo` (Rust) — APK'dan paket/sürüm/manifest okur, `repo.json` + `index.min.json` yazar,
APK'yı `repo/apk/` altına kopyalar. CI (`build-video.yml`) her derlemede bu dosyaları commit eder.

## Mega depo (CloudStream + JAR, Aniyomi hariç)

`pulsar video-mega` (CI: `.github/workflows/mega.yml`) CloudStream pluginlerini ve Kototoro JAR'ını
bu klasörde birleştirir; **Aniyomi depoları birleştirilemez** — Kototoro `apk` alanını dosya adı kabul
edip indirmeyi `<depo-kök>/apk/<apk>` olarak kurar (`ExtensionRepoService.kt:421-422`,
`ExtensionInstallService.kt:96-101`); uzak kayıtların `apk` alanı mutlak URL olduğu için birleşik
indekste 404 verir — bu yüzden harici Aniyomi depolarını ayrı ekle, CloudStream ve JAR birleşik gelir.
Harici Aniyomi depoları:

- `https://raw.githubusercontent.com/yuzono/anime-repo/repo/index.min.json` (248 eklenti)
- `https://raw.githubusercontent.com/aniyomiorg/aniyomi-extensions/repo/index.min.json` (3 eklenti)

Çıktılar: `repo/index.min.json` **yalnız** kendi eklentimizi taşır (göreli `apk` + pakete göre 9/18 `sources`);
`cs/repo.json` + `cs/plugins.json` CloudStream birleşimi (`url` mutlak); `jar/index.min.json`
(`apk` = `plugin.jar`, göreli) + indirilmiş `jar/apk/plugin.jar`; `mega-report.json` harici/atlanan
kayıtları "harici depo olarak eklenmeli" diye işaretler.

## Paketler

| Paket | applicationId | nsfw | Kaynaklar |
|---|---|---|---|
| **Pulsar Video** | `eu.kanade.tachiyomi.animeextension.all.pulsarvideo` | `0` | `ContentType.VIDEO` parser'ları + config (GogoAnime/AniWorld) — indekste 9 |
| **Pulsar Video 18+** | `eu.kanade.tachiyomi.animeextension.all.pulsarvideo18` | `1` | `ContentType.HENTAI_VIDEO` parser'ları — indekste 18 (config kaynakları normal kayda yazılır) |

## Kaynak durumu (2026-11-21)

| Kaynak | Durum | Kanıt / sebep |
|---|---|---|
| `gogoanime.onl` | **yayında (ölçülmüş)** | liste 57 → bölüm `ul#episode_related` → hoster `a[data-video]` (base64) → vidmoly embed → `master.m3u8` **200 `application/vnd.apple.mpegurl`** |
| `aniworld.to` | **yayında (ölçülmüş)** | liste 63 → bölüm 7 (`a[data-episode-id]`) → hoster 8 (`a.watchEpisode`) → `/redirect/...` → vidmoly → `master.m3u8` **200 `application/vnd.apple.mpegurl`** |
| `animesuge.lol` | yok — embed'de düz m3u8 yok, çözücü yok | `player.fairuseonly.xyz/embed` 200, gövdede m3u8/mp4 0; Kototoro'da fairuseonly çözücü yok |
| `animepahe.com` | yok | Cloudflare WAF her uçta 403 |
| `allanime.day` | yok | kök 301 döngüsü; içerik `allmanga.to` Nuxt + GraphQL |
| `hianime.to` | yok | DNS çözülüyor, TCP el sıkışması yok (ağ engeli) |
| `animekai.to` | yok | park (satılık alan adı) |
| `animesuge.to` | yok | NXDOMAIN (canlı kardeş `.lol`) |
| `9anime.org.lv` | kaldırıldı | video çözülemedi (player JS, host çözücü yok) |

Referans repo (gerçek anime eklentileri): `salmanbappi/sb-extensions-source` — `src/en` altında
`gogoanime`, `aniwave`, `animepahe`, `hianimes`, `zorotv`, `allanime`, `animesuge`, `miruro` modülleri.

## Şema (`data/video-catalogue.json`)

```
id, name, lang, nsfw, domain, baseUrl, engine="video", status, config: {
  listPath, itemSelector, titleAttr, coverSelector,
  episodeSelector, episodeNameAttr, searchUrl,
  hosterSelector, hosterUrlAttr, hosterUrlBase64,   // embed/link hoster'lar
  videoSelector, videoJsonSelector, userAgent,
  proxyUrl, dnsOverHttps, tlsFragment, tlsFragmentSize
}
```

Aşamalar: **liste → detay → bölüm → video**. `hosterListParse` URL'yi şu sırayla üretir:
`hosterUrlAttr` → `<a href>` → `<iframe src>` → çocuk `a`/`iframe`. Video adımı üç biçimi destekler:
doğrudan `.m3u8`/`.mp4`, `<iframe src>` embed, JSON `sources[]`.

`config` nesnesi **boş** kayıtlar kataloğa yazılsa da fabrikada oluşturulmaz (`PulsarVideoSourceFactory`),
yani ölçülmemiş kaynak kullanıcıya görünmez.

## Kısıtlar (bilinen)

- DRM'li kaynaklar (Netflix/Disney/CR) kapsam dışı.
- AES-128 HLS: anahtar ucu ayrı istek ister; motor desteği eklenmeli.
- Embed çözücüler site başına değişir; obfuscated player'larda `hosterExtractor` (Kototoro'nun gömülü
  CloudStream çözücüleri) gerekir — stok Aniyomi'de bu sınıflar yoktur.
- Bu ağda HLS/SNI engeli yaygın. Video sınıfı manga motoruyla aynı katmanları uygular:
  **sistem DNS'i → DoH yedeği** (çözülemezse), **TLS reset/trust-anchor yakalayan interceptor**
  (istek parçalı ClientHello ile bir kez tekrarlanır) ve **boş sonuç yedeği** (engel sayfası
  200 dönerse aynı çağrı DoH-öncelikli istemciyle tekrarlanır). `dnsOverHttps`/`tlsFragment`
  config alanları tek tek de açılabilir.
- **Kapak ve video oynatma** uygulamanın kendi istemcisinden geçer; eklentinin DoH/TLS katmanı
  bu isteklere uygulanmaz. Görsel/akış sunucusu SNI ile engelliyse kapak ve oynatma cihaz
  tarafında düşer — kaynak listesi/ayrıntısı çalışsa bile (2026-11-23 cihaz testi: Jable,
  HohoJ, 黄果短剧).
