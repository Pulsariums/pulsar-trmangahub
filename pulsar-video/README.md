# pulsar-video — video (anime) kaynak paketi

Manga paketlerinden bağımsız, **Aniyomi formatında** ayrı bir eklenti. Kototoro ve Aniyomi,
`tachiyomi.animeextension` feature'ı olan APK'ları yükler
(`AniyomiExtensionLoader.kt`: feature `tachiyomi.animeextension`, anahtarlar `.class`, `.factory`, `.nsfw`).

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
- `index.min.json` — eklenti dizisi (`name, pkg, apk, lang, code, version, nsfw, sources[]`).
  `sources` alanı `data/video-catalogue.json`'daki config'i dolu kayıtlardan üretilir; boş kalırsa
  Kototoro "0 kaynak" gösterir ve kuruluma geçmez.

Sürüm kuralı: `versionName = <lib>.<yama>`. Kototoro lib aralığı **12–16**
(`AniyomiExtensionLoader.LIB_VERSION_MIN/MAX`; sürümü `versionName.substringBefore('.')` ile okur),
bu yüzden sürümler `16.x`. `versionCode` her yayında artmalı — aksi hâlde kurulu kullanıcı güncelleme görmez.

Üretim: `pulsar video-repo` (Rust) — APK'dan paket/sürüm/manifest okur, `repo.json` + `index.min.json` yazar,
APK'yı `repo/apk/` altına kopyalar. CI (`build-video.yml`) her derlemede bu dosyaları commit eder.

## Kaynak durumu (2026-11-21)

| Kaynak | Durum | Kanıt / sebep |
|---|---|---|
| `gogoanime.onl` | **yayında (ölçülmüş)** | liste 57 → bölüm `ul#episode_related` → hoster `a[data-video]` (base64) → vidmoly embed → `master.m3u8` **200 `application/vnd.apple.mpegurl`** |
| `animesuge.lol` | kısmi | liste 63 / bölüm 27; embed tek `<iframe>`, video obfuscated player + crypto-js → host çözücü gerekir |
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
- Bu ağda HLS/SNI engeli yaygın; manga motorundaki otomatik DoH + TLS parçalama yedeği video sınıfında
  henüz yok (yalnız config ile `dnsOverHttps`/`tlsFragment` açılabiliyor).
