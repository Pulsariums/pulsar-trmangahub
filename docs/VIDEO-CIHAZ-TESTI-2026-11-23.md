# Video — cihaz testi incelemesi (2026-11-23)

Kaynak: kullanıcının Kototoro kaynak testi, iki koşu (`kototoro-source-test-1795453930.json`
17:12, `...-1795454028.json` 17:13). Kapsam 20 kaynak (normal paketten GogoAnime + AniWorld,
18+ paketin tamamı). Ölçüt: liste → kapak → detay → bölüm → sayfa → arama.

**Sonuç: 2/20 geçti, 18 düştü.** Geçenler: **KanAV** ve **94MT** (ikisi de parser kaynağı;
JSON yalnız düşenleri listeliyor, `total=20, passed=2`).

## Hata sınıfları (iki koşu birlikte)

| Sınıf | Kaynaklar | Koşu 1 | Koşu 2 |
|---|---|---|---|
| Liste boş / `Connection reset` | 85PO, 91Pinse, ACG漫画网动画, Cosxplay, Erome, FPO.XXX, Hanime1, Xanimu | **Liste boş** (200 + engel sayfası) | **Connection reset** |
| `Trust anchor for certification path not found` | HentaiCloud, MissAV | liste | liste |
| İkisi arasında gidip gelen | HentaiPlay, PlayVids | trust anchor | reset |
| Detay 404 | MemoJAV | `https://memojav.org/NSFS-530` | aynı |
| Kapak/sayfa ağ hatası | HohoJ (kapak+sayfa), Jable (kapak) | 200 text/html / reset | trust anchor |
| Kapak `Content-Type` | 黄果短剧 (`binary/octet-stream`) | kapak | kapak |
| Arama desteklenmiyor | AniWorld, GogoAnime | arama | arama |
| Kapak yok | GogoAnime | kapak | kapak |

Ortak nokta: **aynı kaynak bir koşuda "liste boş", diğerinde "reset"** veriyor. Bu, kaynak
ayrıştırıcısının değil **ağ katmanının** imzası: istek bazen engel sayfasına (200), bazen
RST'ye düşüyor.

## Masaüstü karşılaştırması (aynı parser'lar, temiz ağ)

`FullProbe` (kototoro-parsers doğrudan, `.work/vid-device/desktop-adult.log`):

| Kaynak | Liste | Kapak | Sayfa | Cihazdaki sınıf |
|---|---:|---:|---:|---|
| 85PO | 30 | 30/30 | 13 | liste boş / reset |
| 91Pinse | sistem DNS'te yok (DoH çözüyor) | — | — | liste boş / reset |
| ACG漫画网动画 | 27 | 27/27 | 3 | liste boş / reset |
| Cosxplay | 24 | 24/24 | 1 | liste boş / reset |
| Erome | sistem DNS'te yok (DoH çözüyor) | — | — | liste boş / reset |
| FPO.XXX | 20 | 20/20 | 1 | liste boş / reset |
| Hanime1 | 24 | 24/24 | 6 | liste boş / reset |
| HentaiCloud | 23 | 23/23 | 2 | trust anchor |
| HentaiPlay | 513 | 0/513 | 3 | trust anchor / reset |
| HohoJ | 24 | 24/24 | 1 | kapak+sayfa ağ hatası |
| Jable | 24 | 24/24 | 1 | kapak ağ hatası |
| MissAV | 53 | 53/53 | 1 | trust anchor |
| PlayVids | 24 | 24/24 | 1 | trust anchor / reset |
| Xanimu | 24 | 24/24 | 1 | liste boş / trust anchor |
| 黄果短剧 | 20 | 20/20 | 1 | kapak `octet-stream` |
| MemoJAV | 10 | 10/10 | 1 (`master.m3u8`) | detay 404 |
| AniWorld (parser) | 115 | 88/115 | 12 | — (cihazda config AniWorld test edildi) |

Yani **parser'lar sağlam**; cihazda düşen adımlar ağ kaynaklı.

DNS kanıtı: bu makinede de sistem DNS'i `91pinse.com`, `erome.com` için
`UnknownHostException` veriyor; **DoH aynı adları çözüyor** ve DoH ile çekilen sayfa gerçek
içerik dönüyor (`91pinse.com` → 200, 69 KB, doğru `<title>`). Sertifika zincirleri geçerli
(`openssl`: Google Trust Services / Let's Encrypt / Sectigo) — cihazdaki trust-anchor, DNS'in
sahte adres döndürmesi ya da araya giren katmanın kendi sertifikası.

## Yapılan düzeltmeler (16.14 / versionCode 16)

1. **DoH-öncelikli yedek** — `DohFallbackDns(preferDoh = true)`. İlk deneme sistem DNS'iyle
   hızlı kalır; TLS hatasından sonraki yedek istemci (parçalı ClientHello) **her zaman DoH**
   ile gerçek IP'yi alır. `TlsFragmentSticky` ile host 30 dk yedek istemciye sabitlenir.
2. **Boş sonuç yedeği** (`PulsarKotatsuVideoSource.parserCall`) — liste boş dönerse ya da
   istisna atarsa aynı çağrı DoH-öncelikli istemciyle **bir kez** tekrarlanır; başarılıysa
   kaynak o andan sonra yedek istemciye sabitlenir. "Liste boş" sınıfı (200 + engel sayfası)
   TLS hatası üretmediği için eski interceptor'a hiç takılmıyordu.
3. **`SAnime.url` artık önce `publicUrl`** — MemoJAV'ın `/NSFS-530` kimliği yerine
   `/video/NSFS-530` sayfası kullanılır (404 → 200).
4. **Arama** — GET/POST şablonu + JSON yanıt modu:
   - GogoAnime: `https://gogoanime.onl/search?keyword={query}` (form action'ı ölçüldü).
   - AniWorld: `POST https://aniworld.to/ajax/search` gövde `keyword={query}` → JSON
     `[{title, description, link}]`; `/search?q=` sunucu tarafında sonuç döndürmüyor (JS).
5. **Kapak** — GogoAnime listesinde görsel yok; ilk 6 kart için detay sayfasındaki
   `og:image` ile tamamlanır (6 sn bütçe, URL bazında önbellek). Arama sonuçlarında kapak
   zaten `.img img` içinde.

## Doğrulama (16.14)

- CI: `build-video.yml` run **45230025334** → success.
- Yayın: `repo/index.min.json` → iki kayıt **16.14 / code 16**, `nsfw` 0/1, kaynak 9/18.
- APK'lar: `...pulsarvideo.apk` 1 906 063 B **200**, `...pulsarvideo18.apk` 1 906 063 B **200**
  (md5 farklı: `08fe156b…` / `77103114…`).
- DEX'te yeni kod doğrulandı: `ajax/search`, `searchJsonTitle`, `keyword={query}`,
  `preferDoh`, `X-Pulsar-Tls-Retry`.

## Bilinen sınır (düzeltilemez)

- **Kapak ve video oynatma** uygulamanın kendi istemcisinden geçer; eklentinin DoH/TLS
  katmanı bu isteklere uygulanmaz. Jable/HohoJ kapakları, 黄果短剧 `octet-stream` kapağı bu
  yüzden cihazda düşebilir.
- HentaiPlay parser'ı hiç kapak döndürmüyor (masaüstünde 0/513).
- MissAV/Jable gibi Cloudflare arkasındaki siteler cihazda "Just a moment" challenge'ı
  dönebilir; eklentide JS yok.
