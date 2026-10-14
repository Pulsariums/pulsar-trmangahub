# PC testi (Windows)

`calistir.cmd` çift tıkla ya da cmd'de çalıştır. Kurulum gerekmez (PowerShell + curl.exe Windows 10/11'de hazır).

- `calistir.cmd` — 171 kaydın hepsi
- `calistir.cmd -Kapsam yayinda` — yalnız yayındakiler
- `calistir.cmd -Sadece golge,nyx` — adında/alan adında bu geçenler

Her site için liste sayfası kendi IP'nle çekilir ve motorun liste işareti aranır.
Sonuçlar: `tamam`, `yapi_degisti` (site açılıyor ama parser eski yapıya göre), `cloudflare`, `dns`, `baglanti`, `ssl`,
`zaman_asimi`, `baska_siteye_yonlendi`, `satilik_park`, `http_hata`, `acildi` (motor bilinmiyor).
Bu test JAR'ı çalıştırmaz; sitenin JAR'ın göreceği listeyi senin ağından verip vermediğini söyler.
Sonuç `pc-sonuc-*.json` olarak yanına yazılır (depoya gönderilmez, `device.json`'u etkilemez).
