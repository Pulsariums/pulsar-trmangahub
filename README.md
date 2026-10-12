# pulsar-trmangahub

Manga kaynaklarını Mihon (keiyoushi), Kotatsu (kotatsu-parsers-redo) ve Nyora
(nyora-data-driven) üzerinden toplar, domainlerini sınar, ölenler için alternatif arar ve
yayınlanabilir kaynak listelerini üç bölüme ayırarak üretir. Her bölüm Kototoro'ya ayrı bir depo
adresi olarak eklenebilir.

## Kototoro'ya eklenecek adresler

| Bölüm | Adres | İçerik |
|---|---|---|
| turkce/jar | `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/turkce/jar` | Yalnız Türkçe (tr_native) kaynaklar, JAR |
| turkce/mihon | `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/turkce/mihon` | Türkçe Mihon APK aynası (keiyoushi'den) |
| global/jar | `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/global/jar` | Tüm diller (Kotatsu-Redo parser'ları), JAR |
| ozel/jar | `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/ozel/jar` | Kaynak ekle akışıyla üretilen Türkçe özel siteler, JAR |

Bu adresler yalnızca depo herkese açık (public) iken çalışır.

**Önemli:** Eski `.../main/repo` ve `.../main/repo-mihon` adresleri kaldırıldı. Daha önce
eklenmişse Kototoro'daki depoyu silip yukarıdaki yeni adresle yeniden ekleyin.

Global Mihon için Keiyoushi resmi deposunu kullanın. Tüm dillerin APK aynası binlerce APK
içerdiği için bu depoda tutulmaz.

## Bölümler

- **turkce/**: yalnızca `tr_native` kaynaklar. `turkce/jar` (JAR deposu) ve `turkce/mihon`
  (Mihon APK aynası) burada.
- **global/**: tüm diller. Yalnızca JAR (`global/jar`). Her kaynağın `lang` alanı kendi dilidir,
  depo düzeyindeki `lang` ise `all`.
- **ozel/**: `Kaynak ekle` akışının ürettiği ve probe'dan geçmiş yalnızca Türkçe özel siteler.
  Üretilmiş parser yoksa `ozel/jar/index.min.json` `[]` olur.

Her bölüm kendi klasöründe `index.min.json`, `apk/plugin.jar` (varsa), `build_info.json` ve
`README.md` içerir.

## Otomatik kontrol

Akış (sync.yml, 6 saatte bir):

```
[sync.py]       Mihon, Kotatsu (tüm diller), Nyora, sources/custom -> data/upstream_tr.json
    v
[probe.py]      her domain: HTTP durumu, motor parmak izi, işlevsel liste kontrolü
    -> data/probe_results.json
    v
[alternatives.py]  dead / parked / functional=false domainler için aday ara (yalnızca turkce)
    v
[build.py]      iki bölüm: sources/tr (tr_native) ve sources/global (tüm scope)
                her bölüm için ayrı SAFETY_RATIO; biri tripse hiçbir dosya yazılmaz (exit 2)
```

Yayın kuralı: yalnızca probe'da `ok` ve işlevsel kontrolü geçen (`published`) kaynaklar
yayınlanır. Karantina, `failing`, `unverified` ve `cf_protected` kaynaklar varsayılan olarak
girmez (`include_unverified` ile girer). Kurallar `scripts/rules.py` içindedir.

- `sources/tr/` yalnızca Türkçe kaynakları tutar; `turkce/jar` ve `turkce/mihon` bundan beslenir.
- `sources/global/` tüm kaynakları tutar; `global/jar` bundan beslenir.
- `sources/custom/` ve `generated/` `Kaynak ekle` akışının çıktısıdır; `ozel/jar` bunlardan derlenir.

## Action'lar ve seçenekleri

| Workflow | Tetikleyici | Seçenekler | Çıktı |
|---|---|---|---|
| `sync.yml` (Senkron: kaynakları güncelle) | 6 saatte bir, elle | `dry_run`, `fail_threshold` (1/2/3/5, varsayılan 3), `safety_ratio` (40/60/80/off, varsayılan 40), `run_alternatives`, `refresh_kotatsu` | `sources/tr`, `sources/global`; run özeti; `sync-data` artifact'ı |
| `health-check.yml` (Sağlık kontrolü) | 12 saatte bir, elle | `engine_filter`, `status_filter`, `domains` | Run özeti; `health-data` artifact'ı; commit yok |
| `build-jar.yml` (Jar derle: Kototoro JAR depoları) | 6 saatte bir, elle | `bolum` (hepsi/turkce/global/ozel, varsayılan hepsi), `mode` (alive/all_tr), `include_broken`, `apply_alternatives`, `include_unverified`, `force`, `publish` | `turkce/jar`, `global/jar`, `ozel/jar`; her bölüm ayrı commit |
| `build-mihon.yml` (Mihon deposu: Türkçe APK aynası) | 6 saatte bir, elle | `include_unverified`, `publish` | `turkce/mihon` |
| `add-source.yml` (Kaynak ekle: site linkinden üret) | elle | `url`, `name`, `format` (both/jar/mihon), `engine`, `register` | `generated/` ve `sources/custom/` (register açıksa commit) |

Zamanlanmış çalıştırmalarda girdi yoktur ve varsayılanlar kullanılır. `build-jar.yml` bölümleri
sırayla (`max-parallel: 1`) derler; her bölüm temiz bir Kotatsu-Redo kopyasıyla başlar.

## Kaynak ekle ve ozel/

1. `add-source.yml` ile bir site adresi verin. Motor tanınırsa `generated/<domain>/jar/<Sınıf>.kt`
   (ve Mihon şablonu) üretilir, `register` açıksa `sources/custom/sources.json` kaydı yazılır.
2. Sonraki `sync.yml` çalışması domaini probe eder. Domain `published` olursa ozel bölümü o
   parser'ı alır.
3. `build-jar.yml` içinde `ozel` bölümü, yalnızca yayınlanabilir domainlerin `generated/`
   dosyalarını upstream ağacına kopyalar, her dosyanın `@MangaSourceParser` ile kayıtlı
   olduğunu doğrular ve id çakışmasında derlemeyi durdurur. Upstream seçimi yapılmaz
   (`--mode none`).
4. Uygun parser yoksa `ozel/jar/index.min.json` `[]` olur ve derleme yapılmaz.

Motor tanınmayan siteler için kod üretilmez; bu siteler elle yazılmalıdır.

## Nasıl çalıştırılır

```
pip install requests
python scripts/sync.py
python scripts/probe.py
python scripts/alternatives.py
python scripts/build.py
python scripts/analyze_site.py --url https://ornek.com
python3 -I -m unittest discover -s tests
```

Testler ağa çıkmaz; HTTP ve probe sahte (mock) verilerle çalışır. `tests/fake_probe.py`
deterministik sahte probe verisi üretir; bu veri canlı sonuç değildir.

## Dizin yapısı

| Yol | İçerik |
|---|---|
| `turkce/jar/`, `turkce/mihon/` | Türkçe JAR deposu ve Mihon APK aynası |
| `global/jar/` | Tüm diller JAR deposu |
| `ozel/jar/` | Özel Türkçe siteler JAR deposu |
| `sources/tr/` | Türkçe kaynak listesi: `sources.json`, `published.json`, `REPORT.md` |
| `sources/global/` | Tüm kaynak listesi: `sources.json`, `published.json`, `REPORT.md` |
| `sources/custom/` | Kaynak ekle akışının kayıtları |
| `generated/` | Kaynak ekle akışının Kotlin/Gradle iskeletleri |
| `data/` | Çalışma verisi (git'e girmez) |
| `scripts/` | Sync, probe, alternatif, build, JAR ve Mihon yayın scriptleri |
| `tests/` | Birim ve uçtan uca testler |

## Bilinen sınırlar

- Depo private iken raw linkler yetkisiz erişilir; depo public yapılınca çalışır.
- Global bölümün ilk çalışması henüz yapılmadı: `global/jar/index.min.json` şimdilik `[]`.
  Tüm dillerin probe'u ve JAR derlemesi süre olarak uzun sürebilir (timeout 60 ve 90 dakika).
- Kotatsu-Redo tam derlemesi başarısız olursa yedek yol yalnızca yamalarla derler. Bu durumda
  jar, dizinde listelenenden fazla parser içerebilir (mevcut davranış).
- Alternatif arama yalnızca Türkçe kaynaklar için yapılır; global bölümde ölen domainler için
  alternatif aranmaz.
- Sağlık kontrolü varsayılan olarak yalnızca Türkçe kaynakları probe eder.
- `ozel/` parser'ları ve global derleme bu değişiklikte Actions'ta henüz çalıştırılmadı.
  İlk çalıştırmada derleme ve KSP kaydı doğrulanmalıdır.
- Şablonların gerçek siteye karşı derlenip çalıştığı doğrulanmamıştır (önceki sınırla aynı).
