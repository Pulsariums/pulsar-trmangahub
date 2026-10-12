# Kaynak şablonları

`scripts/analyze_site.py` bu klasördeki dosyaları `generated/<domain>/` altına yazar.
Şablonlar gerçek upstream kaynaklarından kopyalanıp yer tutucularla düzenlendi; sözdizimi elle
uydurulmadı. Kaynaklar 2026-10-12 tarihinde `git clone --depth 1` ile alındı:
`keiyoushi/extensions-source` ve `KotatsuApp/kotatsu-parsers`.

## Engine -> şablon

| Motor | Mihon şablonu | Jar şablonu |
|---|---|---|
| madara | `mihon_madara/` | `jar_madara.kt` |
| mangathemesia | `mihon_mangathemesia/` | `jar_mangareader.kt` (Kotatsu'da MangaReader) |
| initmanga | `mihon_initmanga/` | yok |

## Kaynak dosyalar

| Şablon | Gerçek kaynak (repo içi yol) |
|---|---|
| `mihon_madara/build.gradle.kts` | keiyoushi `src/tr/diamondfansub/build.gradle.kts` |
| `mihon_madara/source.kt` | keiyoushi `src/tr/diamondfansub/src/eu/kanade/tachiyomi/extension/tr/diamondfansub/DiamondFansub.kt` |
| `mihon_mangathemesia/build.gradle.kts` | keiyoushi `src/tr/gafeland/build.gradle.kts` |
| `mihon_mangathemesia/source.kt` | keiyoushi `src/tr/gafeland/src/eu/kanade/tachiyomi/extension/tr/gafeland/Gafeland.kt` |
| `mihon_initmanga/build.gradle.kts` | keiyoushi `src/tr/siyahmelek/build.gradle.kts` |
| `mihon_initmanga/source.kt` | keiyoushi `src/tr/siyahmelek/src/eu/kanade/tachiyomi/extension/tr/siyahmelek/Siyahmelek.kt` |
| `jar_madara.kt` | kotatsu `src/main/kotlin/org/koitharu/kotatsu/parsers/site/madara/tr/PiedPiperFansubyy.kt` |
| `jar_mangareader.kt` | kotatsu `src/main/kotlin/org/koitharu/kotatsu/parsers/site/mangareader/tr/MangaKoleji.kt` |

## Yer tutucular

| Yer tutucu | Değer |
|---|---|
| `{{NAME}}` | kaynak adı (`"`, `\` ve `$` çıkarılmış) |
| `{{CLASS}}` | PascalCase ASCII sınıf adı (Türkçe harfler katlanır) |
| `{{PKG}}` | küçük harf paket adı (`sync.make_key`) |
| `{{DOMAIN}}` | domain |
| `{{BASEURL}}` | `https://<domain>` |
| `{{LANG}}` | `tr` |
| `{{ID}}` | sınıf adının büyük harfli hali (Kotatsu `MangaParserSource` değeri) |
| `{{TITLE}}` | kaynak adı |

## Bilinçli sapmalar

- Sınıf gövdeleri boşaltıldı. Diamond Fansub ve Siyah Melek'teki siteye özel override'lar
  (tarih biçimi, seçiciler) çıkarıldı. Yalnızca initmanga şablonunda üç slug kaldı
  (`manga`, `recently-updated`, `manga-ranking`); site farklıysa elle düzeltilmeli.
- `versionCode = 1` ve `ContentWarning.SAFE` sabit. NSFW kaynaklar elle değiştirilmeli.
- Madara jar şablonunda `ContentType.HENTAI` ve `ContentType` importu çıkarıldı. `datePattern`
  ve sayfa boyutu (`18`) PiedPiperFansubyy'den alındı.
- Mihon paket adı her zaman `eu.kanade.tachiyomi.extension.tr.<pkg>`; keiyoushi'nin `tr` deseni.
- Kotatsu `MangaParserSource` enum'u KSP ile üretilir (`kotatsu-parsers-ksp`). `{{ID}}` değeri
  anotasyondaki ID ile aynı olmalıdır; script bunu sağlar.
- Bu şablonlar derlenmedi ve canlı sitelerle denenmedi.
