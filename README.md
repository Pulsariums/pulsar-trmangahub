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
python3 -m unittest discover -s tests
```

Testler ağa çıkmaz; HTTP ve probe sahte (mock) verilerle çalışır. `tests/fake_probe.py`
deterministik sahte probe verisi üretir; bu veri canlı sonuç değildir.

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
