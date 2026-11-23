# Medya doğrulaması — 2026-11-23

Bugüne kadarki ölçümler "liste > 0, bölüm > 0, sayfa > 0" diyordu; bu **görselin/akışın
gerçekten açıldığını kanıtlamıyor**. Bu turda medya uçları ayrıca indirildi.

## Manga: sayfa görselleri

Yöntem: `HARNESS_MEDYA=1` (yeni). Harness, sayfa listesi bulduğunda ilk görseli **kaynağın
kendi istemcisiyle** (Mihon okuyucuda kullanılan `source.client`) indirir ve
`HARNESS_MEDYA <domain> <kod> <content-type> <boyut> <url>` yazar. Ölçüm 1.6.276 APK'larıyla.

Kapsam: `source-status.json`'dan paketlere atanmış **616 kayıt**
(tr 49, tr18 6, global 259, global18 302); 10 chunk, 5+5 paralel işçi.
Ham: `.work/medya/*.out` + `*.err`.

| Aşama | Sayı |
|---|---:|
| Ölçülen kayıt | 616 |
| `KATALOG_DISI` (motor kaynağı, domain yok — `@name:` gerekir) | 159 |
| `pages>0` | 432 |
| Medya ucu ölçülen | 431 |
| **Gerçek görsel (200/206 + `image/*`)** | **374 (%87)** |

### Görsel olmayan 57 kaydın sınıfları

| Sınıf | Sayı | Yorum |
|---|---:|---|
| `IOException: Cloudflare bypass currently disabled` | 32 | Masaüstü çalışma zamanında WebView CF çözücüsü yok; **cihazda çalışır**, ölçüm yapılamıyor |
| `404 text/html` | 6 | **Gerçek arıza**: görsel adresi yanlış |
| `200 application/octet-stream` | 4 | Gerçek görsel, sunucu tipi yanlış (aşağıda bayt kanıtı) |
| `200 text/plain` | 3 | Aynı sınıf / bazıları boş gövde |
| `UnknownHostException` | 3 | Masaüstü DNS; DoH ile çözülüyor |
| `403 text/xml` / `403 text/plain` | 2 | Hotlink koruması (ganma.jp, pawchive) |
| `523` / `526` | 2 | Origin kapalı / TLS |
| `404 application/json` | 1 | API hatası döndü |
| Content-Type yok (200) | 2 | Gövde indi; tip başlığı yok |

Bayt kontrolü (`-r 0-16`, ilk 8 bayt):

| Domain | Başlık | İlk bayt | Sonuç |
|---|---|---|---|
| eahentai.com | octet-stream | `ffd8ffdb00430008` | JPEG ✓ |
| mangakatana.com | octet-stream | `ffd8ffdb00430008` | JPEG ✓ |
| foamgirl.net | octet-stream | `5249464670a60400` | WEBP ✓ |
| mangaplexe.com | octet-stream | `52494646ce6a0200` | WEBP ✓ |
| manhwaden.com | octet-stream | `52494646882f0200` | WEBP ✓ |
| hentaifc.com | octet-stream | `89504e470d0a1a0a` | PNG ✓ |
| rokuhentai.com | 200 | `3c21444f43545950` | **HTML** ✗ |
| allporncomics.co / readmanga18.com / truyenhentai18.net / truyenhentaiz.net | 404 | `3c68746d6c3e…` | HTML ✗ |
| comichubfree.com / lunarx.to / moondaisyscans.pro | 404 | `3c21444f43545950` | HTML ✗ |
| colorcitotoons.site | 404 | `7b22737461747573` | JSON ✗ |

### Gerçek arızalı 8 kaynak (tamir için ajanlara verildi)

`comichubfree.com`, `lunarx.to`, `moondaisyscans.pro`, `readmanga18.com`,
`truyenhentai18.net`, `truyenhentaiz.net`, `allporncomics.co`, `colorcitotoons.site`,
`rokuhentai.com`. Hepsi `kind=catalogue` → config ile tamir edilebilir.
Öneriler `.work/tamir-medya/<domain>.json` altına yazılıyor; katalog ancak doğrulandıktan
sonra değişecek.

## Video: gerçek akış URL'leri

Yöntem: her parser için `FullProbe` → `getPages` ilk sayfa URL'si → curl ile indirme
(ilk 200 KB, DoH açık). Sistemi DNS'i çözemeyen 4 host için JDK `jdk.net.hosts.file`
ile DoH'dan alınan IP verildi.

| Kaynak | Akış | Sonuç |
|---|---|---|
| 85PO | `…/37952.mp4?v-acctoken=…` | **206 video/mp4** (200 KB) |
| 91Pinse | `cdnawsgoogle.456311.xyz/…/pl.m3u8` | **200 application/vnd.apple.mpegurl** |
| ACG漫画网动画 | `gif.acgnngca.com/…/720p/index.m3u8` | **200 mpegurl** |
| Cosxplay | `xcdn1.nosofiles.com/…_high.mp4` | **200 video/mp4, 32 MB** |
| Erome | `v101.erome.com/…_720p.mp4` | referersiz **403**, `Referer: https://www.erome.com/` ile **206 video/mp4** |
| FPO.XXX | `fpo.xxx/get_file/…/1355167.mp4` | **302 → 200 video/mp4, 13,8 MB** (refererli) |
| Hanime1 | `vdownload.hembed.com/…-720p.mp4` | **200 video/mp4** (referer **gönderilmezse** 403) |
| HentaiCloud | `hentaicloud.com/media/videos/hd/3910.mp4` | **200 video/mp4, 37 MB** |
| HentaiPlay | sayfa url'i boş ("Server 0") | 16.16'da `getPageUrl` ile çözülüyor |
| HohoJ | `video-8.ggjav.com/…/index.m3u8` | **200 mpegurl, 255 KB** |
| Jable | `asf-doc.mushroomtrack.com/hls/…m3u8` | **200 mpegurl** |
| MissAV | `surrit.com/…/playlist.m3u8` | **403** (imzalı/uç bağlantılı, refererle de 403) |
| PlayVids | `cdn-v3.userscontent.net/…/master.m3u8` | **200 mpegurl** |
| Xanimu | `xcdn1.nosofiles.com/…_high.mp4` | **206 video/mp4** |
| 黄果短剧 | `yd-lphu-hls.tjyyjk.cn/…m3u8` | **200, 11 KB** (playlist `text/plain`) |
| MemoJAV | `video10.memojav.net/stream/NSFS-530/master.m3u8` | **200, 23 KB** (playlist) |
| AniWorld | `/redirect/4161619` | **301** → embed (hoster akışı; m3u8 zinciri 21.11'de ölçüldü) |

**13/17 akış doğrudan doğrulandı.** Kalanlar: MissAV imzalı uç 403, HentaiPlay düzeltildi
(ölçüm 16.16 sonrası), AniWorld hoster yönlendirmesi (tasarım gereği).

### Bunun getirdiği düzeltmeler (video 16.16 / code 18)

1. `Video` nesnelerine **Referer (site kökü) + UA** eklendi. Kanıt: Erome referersiz 403,
   refererli 206; FPO refererli 302→200.
2. Sayfa url'i boşsa **`getPageUrl`** ile çözülür (HentaiPlay üç sayfayı da kaybediyordu).
3. `headersBuilder` UA + Referer.

## Sınırlar

- Kapak ve oynatma **uygulama/oynatıcı istemcisinden** geçer; eklentinin DoH/TLS katmanı
  oraya uygulanmaz (manga sayfa görselleri `source.client` ile geçer — orada uygulanır).
- Masaüstü harness'ta WebView CF çözücüsü yok; 32 kayıt bu yüzden ölçülemiyor.
- MissAV akışı imzalı ve kısa ömürlü; curl ile 403, oynatıcıda oturum çereziyle açılabilir.
