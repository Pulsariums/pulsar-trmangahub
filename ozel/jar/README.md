# Pulsar TR Manga Hub: Özel Kototoro eklentisi

Kaynak ekle akışıyla üretilen, yalnızca Türkçe özel siteler için parser'lar. Üretilmiş parser yoksa dizin boştur ([]).
`.github/workflows/build-jar.yml` iş akışı bu klasörü günceller.

## Kototoro'ya ekleme

1. Kototoro'yu açın ve **Ayarlar → İçerik Kaynakları → Eklentiler → JAR Depoları → Depo ekle** yolunu izleyin.
2. Adres olarak şunu girin:

   `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/ozel/jar`

3. Depo eklendikten sonra kaynaklar Kototoro içinde görünür.

Not: Depo özel (private) iken bu adres çalışmaz. Depo herkese açık (public) yapıldığında çalışır.

## Lisans

Upstream proje Kotatsu-Redo/kotatsu-parsers-redo, GPL-3.0 lisanslıdır. Bu depodaki kaynak
dönüşümleri ve derleme tarifi `.github/workflows/build-jar.yml` ile açıktır.

## Uyarı

Resmi Kotatsu uygulaması harici jar desteklemez. Bu eklentiyi kullanmak için Kototoro gerekir.

## Dosyalar

- `index.min.json`: eklenti dizini
- `apk/plugin.jar`: derlenmiş eklenti (dizin boşsa yok)
- `build_info.json`: derleme bilgileri (parmak izi, upstream commit, sha256)
