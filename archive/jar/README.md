# Pulsar Manga Hub JAR paketleri

Bu depo Kototoro için dört ayrı JAR paketi içerir. Her paket Kototoro'da ayrı olarak indirilebilir.

| Paket | Kapsam |
| --- | --- |
| `tr` | Yalnız Türkçe kaynaklar, NSFW olmayan |
| `tr_nsfw` | Yalnız Türkçe kaynaklar, NSFW |
| `global` | Türkçe dışındaki tüm diller, NSFW olmayan |
| `global_nsfw` | Türkçe dışındaki tüm diller, NSFW |

Kaynak ekle akışıyla eklenen özel Türkçe siteler de NSFW bayrağına göre `tr` veya `tr_nsfw` paketine girer.

## Kototoro'ya ekleme

1. Kototoro'da **Paketler** bölümünü açın.
2. Depo adresi olarak şunu kullanın:

   `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/jar`

3. İstediğiniz paketi seçip indirin.

`index.min.json` tüm paketlerin dizinidir. Paket dosyaları `apk/` altındadır ve
`.github/workflows/build-jar.yml` iş akışı tarafından güncellenir.
