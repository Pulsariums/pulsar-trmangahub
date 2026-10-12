# pulsar-trmangahub

Türkçe manga kaynaklarını Mihon (keiyoushi), Kotatsu (kotatsu-parsers) ve Nyora
(nyora-data-driven) üzerinden toplar, domainlerini sınar, ölenler için alternatif arar
ve yayınlanabilir Türkçe kaynak listesini `sources/tr/` altında üretir.

## Amaç

Kototoro/Mihon tarafında kullanılabilecek, canlı olduğu doğrulanmış Türkçe kaynak
listesini periyodik olarak yenilemek. Ölü veya bozuk kaynaklar yayın listesinden
çıkar, bulunabilirse alternatif domain ayrıca etiketlenir.

## Akış

```
[sync.py]  upstream (Mihon index, Kotatsu git, Nyora catalogue)
    |  -> data/upstream_tr.json
    v
[probe.py]  her domain: HTTP durumu, motor parmak izi, işlevsel liste kontrolü
    |  -> data/probe_results.json
    v
[alternatives.py]  dead / parked / (ok ama functional=false) domainler için aday ara
    |  -> data/alternatives.json
    v
[build.py]  güvenlik şalteri -> sources/tr/sources.json, published.json, REPORT.md
    |  (şalter tetiklenirse: hiçbir dosya yazılmaz, exit 2)
    v
[sync.yml]  6 saatte bir; değişiklik varsa mevcut dalda commit + push;
            exit 2 ise commit yok, "Senkron iptal edildi" issue'su (açık olan varsa yenisi yok)
```

## Veri dosyaları

| Dosya | İçerik |
|---|---|
| `data/upstream_tr.json` | Üç upstream'den birleşik kaynak listesi (domain bazlı) |
| `data/probe_results.json` | Her domainin probe sonucu (status, functional, moved_to) |
| `data/alternatives.json` | Kırık domain -> alternatif (veya denenen adaylar) |
| `data/cache/` | Kotatsu klonu; git'e girmez (.gitignore) |
| `sources/tr/sources.json` | Tüm kaynaklar, `id` = domain |
| `sources/tr/published.json` | Yalnızca yayınlananlar: `mihon[]`, `jar[]`, `via_alternative[]` |
| `sources/tr/REPORT.md` | Özet tablo, alternatifler, bu run'da değişenler |

## Nasıl çalıştırılır

```
pip install requests
python scripts/sync.py
python scripts/probe.py
python scripts/alternatives.py
python scripts/build.py
python scripts/analyze_site.py --url https://ornek.com
python3 -m unittest discover -s tests
```

Testler ağa çıkmaz; HTTP ve probe sahte (mock) verilerle çalışır. `tests/fake_probe.py`
deterministik sahte probe verisi üretir; bu veri canlı sonuç değildir.

## Action'lar ve seçenekleri

| Workflow | Tetikleyici | Seçenekler | Çıktı |
|---|---|---|---|
| `sync.yml` (Senkron: TR kaynaklarını güncelle) | 6 saatte bir, elle | `dry_run` (commit atma), `include_multilang` (tr dışı kaynakları yayınla), `fail_threshold` (1/2/3/5, varsayılan 3), `safety_ratio` (40/60/80/off, varsayılan 40), `run_alternatives` (varsayılan açık), `refresh_kotatsu` (Kotatsu klonunu yenile) | Run özeti (`report.py sync`), `sync-data` artifact'ı (7 gün) |
| `health-check.yml` (Sağlık kontrolü) | 12 saatte bir, elle | `engine_filter` (all/madara/mangathemesia/initmanga/unknown), `status_filter` (all/published/cf_protected_published/failing/quarantined), `domains` (virgülle; boşsa filtrelere göre) | Run özeti (`report.py health`), `health-data` artifact'ı (7 gün); commit yok |
| `add-source.yml` (Kaynak ekle: site linkinden üret) | elle | `url` (zorunlu), `name` (boşsa domainden), `format` (both/jar/mihon), `engine` (auto/madara/mangathemesia/initmanga/custom), `register` (kaydet ve commit at) | Run özeti (`report.py add`), `generated` artifact'ı (7 gün); `register` açıksa `sources/custom/` ve `generated/` commit'lenir |

Elle çalıştırmada seçilmeyen girdiler varsayılanla çalışır. Zamanlanmış çalıştırmalarda
girdi yoktur; `sync.yml` tüm varsayılanları kullanır. `FAIL_THRESHOLD`, `SAFETY_RATIO` ve
`INCLUDE_MULTILANG` ortam değişkenleri scripts tarafından okunur.

## Kaynak ekle

Elle çalıştırılan `add-source.yml` (Kaynak ekle: site linkinden üret) bir manga sitesinin
adresinden kaynak iskeleti üretir. `scripts/analyze_site.py` adresi normalize eder, `probe.py`
ile durumu ve motoru (madara, mangathemesia, initmanga) tespit eder, ana sayfadan dil ve
başlığı okur, `data/upstream_tr.json` içinde aynı domainin olup olmadığına bakar.

Üretir:

- Motor tanınırsa `generated/<domain>/` altında şablondan Mihon kaynağı (`mihon/build.gradle.kts`
  ve Kotlin kaynağı) ve motor için jar parser (`jar/<Sınıf>.kt`, initmanga için yok).
- `data/analyze_result.json`: karar (`verdict`), tespit edilen motor, işlevsel kontrol, dil,
  upstream eşleşmesi ve sıradaki adımlar.
- `register` açıksa `sources/custom/sources.json` kaydı. Bu kayıtlar probe ve sağlık takibine
  girer ama Mihon ya da jar yayın listesine girmez.

Üretmez:

- APK, jar veya herhangi bir derleme yoktur. Üretilen dosyalar kaynak iskeletidir; derleme
  sonraki aşamadır.
- İkonlar (`res/`) yoktur; Mihon derlemesi için eklenmeleri gerekir.
- Site özel seçicileri (tarih, yazar, bölüm listesi) yoktur. Şablonlar varsayılan motor
  davranışını kullanır; gerekirse elle düzeltilir.
- `unsupported_engine` kararında kod üretilmez; motor tanınmayan siteler için özel Kotlin
  kodu yazılması gerekir.
- Şablonların gerçek siteye karşı derlenip çalıştığı doğrulanmamıştır. Actions'ta canlı
  sitelerle denemek gerekir.

Şablonların kaynağı ve sapmaları `scripts/templates/README.md` içindedir.

## Kural tablosu

| Probe durumu | Yayın durumu | Not |
|---|---|---|
| ok, functional != false | `published` | Mihon ve jar listelerine girer |
| ok, functional == false | `quarantined` | Sayfa açılıyor ama liste bulunamadı |
| cf_protected | `cf_protected_published` | Erişilebilir, bot korumalı; listelere girer |
| dead / parked | `quarantined` | Alternatif varsa `alternative` alanı; alternatif `published_via_alternative` olarak `published.json` içinde |
| blocked / other | önceki durum korunur, `unverified: true` | Bu run'da doğrulanamadı; önceki durum yoksa `unverified` |

Alternatif güven düzeyi: `moved_to` ve `altDomains` = high; aynı key = medium; aynı ad = medium;
key benzerliği (>= 0.85) = low. Mihon ve jar paketleri eski domaine bağlı kalır; alternatif
yalnızca bilgi/yönlendirme amaçlıdır.

## Şalter

Bu run'da domainlerin %40'ından fazlası `dead` ise (ağ sorunu olabilir) veya %40'ından fazlası
`blocked` ise `build.py` hiçbir dosyayı değiştirmeden exit code 2 ile çıkar. Workflow commit
atmaz ve "Senkron iptal edildi" issue'su açar.

## Bilinen sınırlar

- Mihon/Kototoro depo URL'si olarak bu repo eklenemez: depo private iken raw linkler yetkisiz
  erişilir. Depo public yapılınca eklenebilir.
- `data/upstream_tr.json` ve `data/probe_results.json` her çalıştırmada zaman damgası
  değiştiği için workflow neredeyse her 6 saatte bir commit atar.
- Upstream'deki `@Broken` işaretleri yayın kararında kullanılmaz; yalnızca probe sonucu belirler.
- Motor parmak izi ve işlevsel kontrol, sitelerin HTML yapısına bağlıdır; site tasarımı
  değişirse yanlış `functional: false` üretebilir.

## Depo bağlantıları

Kototoro ve Mihon'a eklemek için iki adres:

- Kototoro (JAR): `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/repo`
- Mihon (APK): `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/repo-mihon`

Mihon deposu, `.github/workflows/build-mihon.yml` ile 6 saatte bir keiyoushi/extensions
deposundaki Türkçe eklentilerden üretilir (`scripts/mihon_publish.py`).
