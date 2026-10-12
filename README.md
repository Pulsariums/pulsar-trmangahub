# pulsar-trmangahub

Manga kaynaklarını Mihon (keiyoushi), Kotatsu (kotatsu-parsers-redo) ve Nyora
(nyora-data-driven) üzerinden toplar, domainlerini sınar, ölenler için alternatif arar ve
yayınlanabilir kaynakları dört JAR paketi ile Türkçe Mihon APK aynasına dönüştürür.

## JAR: Kototoro'ya ekleme

Tüm JAR paketleri tek depo adresinde toplanır:

`https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/jar`

| Paket | Kapsam |
|---|---|
| `tr` | Yalnız Türkçe kaynaklar, NSFW olmayan |
| `tr_nsfw` | Yalnız Türkçe kaynaklar, NSFW |
| `global` | Türkçe dışındaki tüm diller, NSFW olmayan |
| `global_nsfw` | Türkçe dışındaki tüm diller, NSFW |

Kototoro'ya ekleme:

1. Ayarlar > İçerik Kaynakları > Eklentiler > JAR Depoları > Depo ekle yolunu izleyin ve yukarıdaki
   adresi girin.
2. Paketler listesinden istediğiniz paketi ayrı ayrı indirin.

Eski adresler (`.../main/repo`, `.../turkce/jar`, `.../global/jar`, `.../ozel/jar`) artık yoktur.
Daha önce eklenmişse bu depoları Kototoro'dan silip yukarıdaki yeni adresi ekleyin.

Paketlere yalnızca çalışan kaynaklar (durumu `ok`) girer. Karantinadaki, `failing`,
`cf_protected` ve doğrulanmamış kaynaklar varsayılan olarak yer almaz.

Bu adres yalnızca depo herkese açık (public) iken çalışır.

## Mihon ve global Mihon

- Türkçe Mihon APK aynası ayrıdır: `https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/turkce/mihon`
  (keiyoushi'den).
- Global Mihon için Keiyoushi resmi deposunu kullanın. Tüm dillerin APK aynası binlerce APK
  içerdiği için bu depoda tutulmaz.

## Dizin yapısı

- `jar/`: JAR deposu. `index.min.json` tüm paketlerin dizinidir, `apk/` paket dosyalarını,
  `state/` her paketin girdisini ve derleme bilgisini (`<paket>.entry.json`,
  `<paket>.build_info.json`) tutar.
- `sources/tr/` (tr_native) `tr` ve `tr_nsfw` paketlerini, `sources/global/` (tüm scope) `global` ve
  `global_nsfw` paketlerini besler. Her kaynağın `lang` alanı kendi dilidir.
- `sources/custom/` ve `generated/`: `Kaynak ekle` akışının çıktısıdır; Türkçe özel siteler
  NSFW bayrağına göre `tr` veya `tr_nsfw` paketine girer.

## Otomatik kontrol

Akış (sync.yml, 6 saatte bir):

```
[sync.py]       Mihon, Kotatsu (tüm diller), Nyora, sources/custom -> data/upstream_tr.json
    v
[probe.py]      her domain: HTTP durumu, motor parmak izi, işlevsel liste kontrolü
    -> data/probe_results.json
    v
[alternatives.py]  dead / parked / functional=false domainler için aday ara (yalnızca Türkçe)
    v
[build.py]      iki bölüm: sources/tr (tr_native) ve sources/global (tüm scope)
                her bölüm için ayrı SAFETY_RATIO; biri tripse hiçbir dosya yazılmaz (exit 2)
```

Yayın kuralı: yalnızca probe'da `ok` ve işlevsel kontrolü geçen (`published`) kaynaklar
yayınlanır. Karantina, `failing`, `unverified` ve `cf_protected` kaynaklar varsayılan olarak
girmez (`include_unverified` ile girer). Kurallar `scripts/rules.py` içindedir.

## Action'lar ve seçenekleri

| Workflow | Tetikleyici | Seçenekler | Çıktı |
|---|---|---|---|
| `sync.yml` (Senkron: kaynakları güncelle) | 6 saatte bir, elle | `dry_run`, `fail_threshold` (1/2/3/5, varsayılan 3), `safety_ratio` (40/60/80/off, varsayılan 40), `run_alternatives`, `refresh_kotatsu` | `sources/tr`, `sources/global`; run özeti; `sync-data` artifact'ı |
| `health-check.yml` (Sağlık kontrolü) | 12 saatte bir, elle | `engine_filter`, `status_filter`, `domains` | Run özeti; `health-data` artifact'ı; commit yok |
| `build-jar.yml` (Jar derle: Kototoro JAR deposu) | 6 saatte bir, elle | `bolum` (hepsi/tr/tr_nsfw/global/global_nsfw, varsayılan hepsi), `mode` (alive/all_tr; global paketlerde daima alive), `include_broken`, `apply_alternatives`, `include_unverified`, `force`, `publish` | `jar/` (paket başına ayrı commit) |
| `build-mihon.yml` (Mihon deposu: Türkçe APK aynası) | 6 saatte bir, elle | `include_unverified`, `publish` | `turkce/mihon` |
| `add-source.yml` (Kaynak ekle: site linkinden üret) | elle | `url`, `name`, `format` (both/jar/mihon), `engine`, `register` | `generated/` ve `sources/custom/` (register açıksa commit) |

Zamanlanmış çalıştırmalarda girdi yoktur ve varsayılanlar kullanılır. `build-jar.yml` paketleri
sırayla (`max-parallel: 1`) derler; her paket temiz bir Kotatsu-Redo kopyasıyla başlar.

## Kaynak ekle

1. `add-source.yml` ile bir site adresi verin. Motor tanınırsa `generated/<domain>/jar/<Sınıf>.kt`
   (ve Mihon şablonu) üretilir, `register` açıksa `sources/custom/sources.json` kaydı yazılır.
2. Sonraki `sync.yml` çalışması domaini probe eder. Domain `published` olursa parser, Türkçe
   paketlere girer.
3. `build-jar.yml` içinde `tr` ve `tr_nsfw` paketleri, yalnızca yayınlanabilir domainlerin
   `generated/` dosyalarını upstream ağacına kopyalar; her dosyanın `@MangaSourceParser` ile
   kayıtlı olduğunu doğrular ve id çakışmasında derlemeyi durdurur. NSFW bayrağına göre
   doğru pakete girer.
4. Yayınlanabilir parser yoksa paket indeksten çıkar ve jar üretilmez.

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

## Dizin yapısı (ayrıntılı)

| Yol | İçerik |
|---|---|
| `jar/` | JAR deposu: `index.min.json`, `apk/`, `state/`, `README.md` |
| `turkce/mihon/` | Türkçe Mihon APK aynası |
| `sources/tr/` | Türkçe kaynak listesi: `sources.json`, `published.json`, `REPORT.md` |
| `sources/global/` | Tüm kaynak listesi: `sources.json`, `published.json`, `REPORT.md` |
| `sources/custom/` | Kaynak ekle akışının kayıtları |
| `generated/` | Kaynak ekle akışının Kotlin/Gradle iskeletleri |
| `data/` | Çalışma verisi (git'e girmez) |
| `scripts/` | Sync, probe, alternatif, build, JAR ve Mihon yayın scriptleri |
| `tests/` | Birim ve uçtan uca testler |

## Bilinen sınırlar

- Depo private iken raw linkler yetkisiz erişilir; depo public yapılınca çalışır.
- Global paketlerin ilk çalışması henüz yapılmadı: `jar/index.min.json` şimdilik `[]`.
  Tüm dillerin probe'u ve JAR derlemesi süre olarak uzun sürebilir (timeout 60 ve 90 dakika).
- Kotatsu-Redo tam derlemesi başarısız olursa yedek yol yalnızca yamalarla derler. Bu durumda
  jar, dizinde listelenenden fazla parser içerebilir (mevcut davranış).
- Alternatif arama yalnızca Türkçe kaynaklar için yapılır; global paketlerde ölen domainler için
  alternatif aranmaz.
- Sağlık kontrolü varsayılan olarak yalnızca Türkçe kaynakları probe eder.
- `jar/` düzeni, dört paket ve `Kaynak ekle` parser'ları Actions'ta henüz uçtan uca
  çalıştırılmadı. İlk çalıştırmada derleme ve KSP kaydı doğrulanmalıdır.
- Şablonların gerçek siteye karşı derlenip çalıştığı doğrulanmamıştır (önceki sınırla aynı).
