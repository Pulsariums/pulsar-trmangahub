# Aşama raporu — 15 Kasım 2026 (build 55, sürüm 1.6.55)

Odak: önce Türkçe. Global (361 + 134 kaynak) test edilmedi ve bozuk kaynak dolu; TR bitince sırası gelecek.

## Havuz
- Yukarı akış: Keiyoushi, Nyora katalog, Nyora canlılık, Kotatsu-Redo.
- Motor: 1272 kaynak (295 broken, 121 TR). Katalog: 98 ham → 66 (32 klon elendi).
- Yayında: tr 34, tr18 5, global 361, global18 134, tr_sorunlu 11. Beklemede: 823.
- Son cihaz testi (TR): 39 kaynak, 30 geçti, 8 kaldı, 1 Cloudflare.

## Onarılanlar (build 55, cihazda doğrulanacak)
- Kuroi Manga: HTTP/1.1 sabitleme + IOException yeniden deneme.
- Amanga Planet: GET 403'te 5 deneme.
- Anikiga (katalog): bölümler POST /ajax/chapters/.
- Nyx Scans: -novel kayıtları listeden çıkarıldı.
- OpiaToon: sorun=login.
- Lunar Manga: bölümler API'den, dil önceliği tr, sayfa ?lang=tr.

## Sıradaki
- Adonis (sayfalar), Anikiga (motor sürümü), ShadowCeviri (arama): motordan kataloğa geçiş.
- TilkiScans: Cloudflare, kullanıcı tarafı.
- Ölü DNS / bozuk sertifika: onarılamaz (sarcasmscans, epikman, yaoibar, MangaAy, AyaToon).

## Yeni repolar
- skepsun/kototoro-parsers ve skepsun/k-parsers-r: tek jar; TR'de yeni kaynak yok (k-parsers-r = Kotatsu-Redo yeniden paketi).
- Adaylar: yuzono/manga-repo, komikku-app/komikku-extensions (TR içeriği ölçülecek).

## Kaynak üretici (DeepSeek) tasarımı
Keşif → motor tespiti → en yakın doğrulanmış kayıttan config → curl ile liste/detay/bölüm/sayfa sınaması → başarısız adımı teşhis döngüsü → selector_verified yalnız 4 adım geçince. Tanınmayan motor "beklemede" kalır.
