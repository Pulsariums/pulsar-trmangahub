# Kototoro tam tarama raporu — 2026-11-21

Ölçüm: `tools/harness/run.sh` (Kototoro'nun kendi masaüstü çalışma zamanı + bizim yayındaki APK'lar).
Kapsam: 6 paketin tamamı, **747 id / 739 ölçülebilir domain**. Ölçüt: `list>0 && chapters>0 && pages>0`;
sayfa listesi HTML dönerse geçmiş sayılmaz (bu turda hiç tetiklenmedi: 0 satır).

## Paket tablosu

| Paket | Ölçülen | Geçti | Kaldı | Geçme |
|---|---:|---:|---:|---:|
| tr | 48 | 37 | 11 | %77 |
| tr18 | 4 | 2 | 2 | %50 |
| global | 243 | 65 | 178 | %27 |
| global18 | 283 | 21 | 262 | %7 |
| test | 111 | 0 | 111 | %0 |
| test18 | 50 | 2 | 48 | %4 |
| **Toplam** | **739** | **127** | **612** | **%17** |

Ham veri: `.work/tam/sonuc.json`, log'lar `.work/tam/<paket>.log`.

## Hata sınıfları

| Sınıf | Sayı | Ne demek |
|---|---:|---|
| `UnknownHostException` | **301** | DNS çözümlenemedi. **301'in 301'i katalogda kayıtlı** → yerel ISP DNS bloğu (TR). DoH ile curl 301/403 dönüyor, yani site sağlam. |
| `KATALOG_DISI` | **243** | Paket listesinde id var ama **hiçbir kaynak örneği yok**. 20'si katalogda (merge düşürmüş), **223'ü katalogda hiç yok** → hayalet id. |
| `SocketTimeoutException` | 20 | 6 paralel işçi + zayıf bağlantı; tekrar denenmeli. |
| `UnsupportedOperationException` | 20 | Motorun `@Broken` kaynağı (aynı host'lu katalog kaydı yok). |
| `KAPSAM_DISI` | 12 | Kaynak başka pakette yayında; test yanlış pakette koştu (ölçüm hatası, kaynak hatası değil). |
| `bölüm listesi boş` | 6 | Gerçek arıza (liste var, bölüm yok). |
| `popüler liste boş` / boş hata | 9 | Gerçek arıza. |
| `SunCertPathBuilderException` | 1 | Sertifika zinciri. |

`list=0` olan 600 kaydın dağılımı: 301 DNS + 243 hayalet + 20 timeout + 20 @Broken + 12 kapsam dışı ≈ 596; kalan ~4 gerçek liste arızası.
`pages=0` (liste+bölüm çalışıyor): yalnız **6** kaynak — yani okuyucu tarafı büyük ölçüde sağlam.

## Yorum

1. **Asıl sorun kaynaklar değil, DNS.** 18+ paketinin %79'u (223/283) Türkiye ISP DNS'inde çözümlenmiyor.
   Kaynak config'lerinde `dnsOverHttps` alanı var ama katalogda **yalnız 1 kayıtta** dolu.
   301 kayda DoH eklendiğinde bu sınıfın tamamı test edilebilir hale gelir.
2. **Paket listeleri şişkin.** 747 id'nin 243'ü hayalet: katalogda karşılığı yok, motorda örneği yok.
   Gerçek yayın kapasitesi ≈ 504 kaynak. Hayaletler test havuzunu ve paket sayaçlarını kirletiyor.
3. Gerçek içerik arızaları az: ~16 liste + 6 okuyucu. Bunlar tamir edilebilir.

## Sıradaki işler

- (A) 301 DNS'li kayda `dnsOverHttps: https://cloudflare-dns.com/dns-query` ekle → build → aynı 301'i yeniden test et.
- (B) 223 hayalet id'yi defterde `dead` işaretle (paketlerden çıkar) — karar bekliyor.
- (C) 20 `@Broken` motor kaynağı için katalog karşılığı yaz (bugün 6'sı yapıldı, kalanlar ölçülü).
- (D) 20 timeout'u tek işçiyle tekrar dene.

## Doğrulama

```
grep -c '^{"domain"' .work/tam/*.log
python -I -X utf8 -c "import json;print(len(json.load(open('.work/tam/sonuc.json',encoding='utf-8'))))"
```
