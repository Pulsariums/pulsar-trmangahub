# Pulsar Manga Merkezi: Amaç

## Amaç
- Bilinen tüm dış repolardaki Mihon/Tachiyomi ve JAR (Kotatsu/Kototoro parser) kaynaklarını tek havuzda toplamak.
- Havuzdaki her kaydın ve her alan adının hangi repodan/sürümden geldiğini yazmak.
- Aynı siteleri tekilleştirmek; eski/yeni alan adlarını o sitenin altında gruplamak.
- Havuzda olmayan siteler için, doğrulanmış kaynaklardan ve deneyim hafızasından öğrenen üreticiyle kendi kaynaklarımızı üretmek.
- Her kaynağı Kototoro'da cihaz testiyle doğrulamak; yalnız doğrulananları Nyora tarzı tek APK'da yayınlamak. JAR hattı yok; JAR kaynaklar da APK'ya çevrilir.
- Tamirde öğrenileni deneyim hafızasına yazmak; tamirde ve üretimde yeniden kullanmak.

## Gruplar (5)
`tr`, `tr18`, `global`, `global18`, `test`

- Ana gruba yalnız cihazda geçen kaynak girer.
- Doğrulanmamış, tamiri kesinleşmemiş veya cloudflare/giriş etiketli her şey `test` grubuna gider.
- Kesin ölü hiçbir gruba girmez; havuzda arşiv olarak kalır.

## Aşamalar
0. Repo bulma.
1. Havuz: tekilleştirme, alan adı gruplama, köken yazımı.
2. Test grubunu doldurma ve push.
3. Cihaz raporu analizi:
   - Geçen: grubuna alınır.
   - Tamire yakın: tamir edilir, sonraki teste girer.
   - Uzak: tamir kuyruğuna.
   - Alan adı hatası: diğer repolar + internetle yeni alan adı araştırılır.
4. Döngü (3. aşamayı tekrarla).
5. Üretici:
   - Motor tespiti.
   - En yakın doğrulanmış kayıt + deneyim hafızası.
   - 4 adım curl doğrulaması.
   - Geçmeden test grubuna bile girmez.

## Havuz kayıt şeması
- `site kimliği`
- `dil`
- `nsfw`
- `alan adları`: `[{alan, repo, ilk_gorulme, son_gorulme, durum: canli|tasinmis|olu}]`
- `kokenler`: repo id'leri veya `"pulsar-uretici"`
- `motor`
- `son cihaz sonucu`
- `grup`

## Hedef klasör düzeni (bilgi; dosya taşıma yapılmadı)
- `pulsar-v2/config/upstreams.json`
- `pulsar-v2/data/havuz.json`
- `pulsar-v2/data/durum.json` (şimdilik `source-status.json`)
- `pulsar-v2/data/raporlar/`
- `pulsar-v2/data/tamir.json`
- `pulsar-v2/data/deneyim.json`
- `pulsar-v2/extension/`
- `pulsar-v2/tools/pulsar/`
- Kullanılmayanlar `arsiv/` altına.
