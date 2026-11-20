# pulsar-video — video (anime) kaynak paketi

Bu klasör **ayrı bir eklenti** olacak: manga paketlerinden bağımsız, Aniyomi formatında.
Kototoro ve Aniyomi, `tachiyomi.animeextension` feature'ı olan APK'ları yükler
(`Kototoro/app/.../aniyomi/AniyomiExtensionLoader.kt`: feature `tachiyomi.animeextension`,
nsfw anahtarı `tachiyomi.animeextension.nsfw`).

## Neden Aniyomi formatı

- Kototoro'da **video oynatıcı var**: `DesktopVideoPlayer`, `DesktopVideo`, `DesktopVideoController$changeVideoEpisode`.
- Kototoro **Aniyomi depolarını okuyor**: `core-source/.../extensions/repo/AniyomiExtensionStoreIndex.kt`.
- Yani video için ayrı uygulama gerekmiyor; tek eksik bizim kaynak kodumuz.

## Kaynaklar (Türk değil, global)

Ağ ölçümü (2026-11-20, kullanıcı ağı, masaüstü UA):

| Site | HTTP | Not |
|---|---|---|
| `9anime.org.lv` | **200** (256 KB) | erişilebilir; ilk hedef |
| `gogoanime3.net` | 302 | yönlendirme; hedef ölçülmeli |
| `animepahe.com` | 301 | yönlendirme; hedef ölçülmeli |
| `allanime.day` | 301 | yönlendirme; hedef ölçülmeli |
| `hianime.to` | 000 | ağda kapalı (DPI/engel) |
| `aniwatchtv.to` | 000 | ağda kapalı |
| `animesuge.to` | 000 | ağda kapalı |

Referans repo (gerçek anime eklentileri, Kototoro fork'u değil):
`salmanbappi/sb-extensions-source` — `src/en` altında `gogoanime`, `aniwave`, `animepahe`,
`hianimes`, `zorotv`, `allanime`, `animesuge`, `miruro` modülleri var; video çözümü
(HLS/embed) için desen kaynağı olarak kullanılacak.

## Şema (video-catalogue.json)

Manga `catalogue.json`'ın video eşi; alanlar:

```
id, name, lang, nsfw, domain, baseUrl, engine="video",
config: {
  listPath, itemSelector, titleSelector, coverSelector,
  detailsPath?,
  episodeSelector, episodeNumberAttr?, episodeApiUrl?, episodeApiItems?,
  videoApiUrl?, videoApiItems?, videoFieldUrl?, videoFieldQuality?,
  videoSelector? (iframe/m3u8), videoHostAllow?,
  searchUrl
}
```

Aşamalar: **liste → detay → bölüm → video**. Video adımı üç biçimi destekler:
1. Doğrudan `.m3u8` / `.mp4` (HLS oynatıcı),
2. `<iframe src>` embed (çözücü gerekir),
3. JSON `sources[]` (kalite/etiket ile).

## Yapım adımları (sıradaki turlar)

1. **İskelet**: ayrı repo veya bu repoda `pulsar-video/` Gradle modülü. Aniyomi eklentileri
   `gradle/build-logic` içeren kendi şablonlarıyla derleniyor (`sb-extensions-source` gibi);
   bu yüzden CI'da Aniyomi şablonu klonlanıp modülümüz eklenecek (manga tarafındaki Mihon
   checkout deseninin aynısı).
2. **Tek kaynak sınıfı**: `PulsarVideoSource : AnimeSource` — config'i `video-catalogue.json`'dan okur
   (manga `PulsarSource`'un video eşi).
3. **İlk kaynak**: `9anime.org.lv` — liste/detay/bölüm/video ölçümü, `video-catalogue.json`'a yazım.
4. **Doğrulama**: `tools/harness` benzeri bir video harness'ı (Aniyomi API'siyle) veya cihaz testi.
5. **Yayın**: ayrı repo (`pulsar-video` index) — manga deposunu kirletmeden.

## Kısıtlar (bilinen)

- DRM'li kaynaklar (Netflix/Disney/CR) kapsam dışı.
- AES-128 HLS: anahtar ucu ayrı istek ister; motor desteği eklenmeli.
- Embed çözücüler site başına değişir; her kaynak için ayrı `videoSelector`/çözücü gerekir.
- Kototoro'nun Aniyomi lib sürümü ile APK `tachiyomix.extensionLib` eşleşmeli.
