# Tamir bulguları — 1.6.29 cihaz testi sonrası (2026-11-13)

Tek dosya, ajan başına tek bölüm. Her ajan YALNIZ kendi `<!-- A? -->` işaretini doldurur,
başka bölüme dokunmaz. Yazılan her satır gözlenmiş kanıta dayanır; görülmeyen değer
`BULUNAMADI` yazılır. Uydurma yasak.

## Ortak bilgi (değiştirme)

- Cihaz testi (Kototoro 1.6.29): list → covers → details → chapters → pages → search.
  DETAILS adımı, manga detay sayfasını `baseUrl + manga.url` ile çeker; CHAPTERS adımı
  aynı sayfadan çıkan bölüm listesini ister. Boş liste = adım hatası.
- Eklenti ayrıştırıcısı (`EngineRegistry`):
  - bölüm adayı = yolunda ≥3 parça (veya 2 parça ve ilk parça
    chapter/bolum/bölüm/oku/read/episode), son parçası `…bolum|bölüm|chapter|chap|ch N`
    ya da `^N` / `^N-…` / `^N_…` biçiminde sayı içeren link.
  - sayfa adayı = `<img>` `data-src|data-lazy-src|src`, alt/dosya adında sayfa/page ya da
    `/12.jpg` deseni; logo/icon/avatar/banner/favicon elenir.
- İstek başlıkları: `Referer: <site>/`, masaüstü Chrome 124 UA.

---

## A1 — TrManga (trmanga.com) · bölümler boş

**Cihaz:** list/covers/details/search GEÇTİ, chapters "Bölüm listesi boş".
**Ana oturumun gördüğü:** `https://trmanga.com/webtoon/the-northern-duke-needs-a-warm-hug`
sayfası 184 KB ve içinde 25 adet `href="/webtoon/<slug>/<sayı>"` linki var; masaüstü,
Android ve okhttp UA'larının hepsinde aynı. Yani HTML'de bölümler VAR.

**Aranan cevap:** cihazın 0 bölüm görmesinin sebebi ne? Aşağıdakileri tek tek doğrula:
1. Liste sayfası `/liste` içindeki 2 parçalı linkler hangi ön eklerle geliyor?
   (`/webtoon/<slug>` dışında `/seri/`, `/manga/` var mı?)
2. Detay sayfasındaki bölüm linkleri GERÇEKTEN 3 parçalı mı, yoksa bir kısmı
   `href="76"` gibi göreli mi?
3. Sayfada `li.wp-manga-chapter`, `div.chapter-item`, `div.eph-num` var mı? Varsa
   içlerinde `<a href>` var mı?
4. `/seri/` biçimli bir detay sayfasının (varsa) bölüm linkleri neye benziyor?

**Bölüm linki biçimi:** `href="/webtoon/the-northern-duke-needs-a-warm-hug/1"` · `href="/webtoon/the-northern-duke-needs-a-warm-hug/21"` (3 parçalı, sayı sonda)
**Bölüm link sayısı:** 25 (tekil 21; numaralar 1–21)
**Göreli (yalnız sayı) link:** 0 (yok)
**Madara sınıfları:** 0 (`wp-manga-chapter`, `chapter-item`, `eph-num` hiçbiri geçmiyor)
**Liste sayfası ön ekleri:** `/liste` → 302 Location: `/` (gövde boş); ana sayfada: /webtoon 125, /tur 105, /fansub 15, /oneri 9, /panel 8, /en 4 — `/seri/` ve `/manga/` yok
**/seri/ detayı:** BULUNAMADI (5. adımda `/seri/` veya `/manga/` biçimli link çıkmadı)
**Sonuç:** Tüm bölüm linkleri sayfada gerçek `<a href>` olarak (25/25) ve ayrıştırıcı kuralının istediği `≥3 parça + son parça ^N` biçiminde duruyor; yani HTML'de var, ayrıştırıcı kuralı bunu yakalar, sebep ayrıştırıcı değil.
**Kanıt:** `href="/webtoon/the-northern-duke-needs-a-warm-hug/1"` ve `href="/webtoon/the-northern-duke-needs-a-warm-hug/21"` (ADIM1 ham çıktısı)
`ADIM2 toplam: 25` · `ADIM2 tekil: 21` · `ADIM3 goreli sayi href: 0` · `ADIM4 Madara sinif: 0` · `/liste http=302 size=0`

---

## A2 — XCOMIC (xcomic.me) · bölümler boş

**Gömülü JSON:** VAR — Qwik SSR durumu: `<script type="qwik/state" q:instance="...">` + `<script q:func="qwik/json">`; bölüm düğümü `chapterNode_up_to` → `data`. Ancak TAM liste yok: 95.938 baytlık HTML'de yalnız 3 `/chapter/<id>` ve 2 "Chapter N" adı geçiyor.
**API uç noktası:** BULUNAMADI — ham HTML'de `/api/...` yok (tek eşleşme `api.whatsapp.com` paylaşım linki), `/title/dgoz5m/q-data.json` 404 döndü, `application/qwik-json` POST'u SPA HTML döndü.
**Yöntem/başlık:** GET + `User-Agent` + `Referer: https://xcomic.me/` (yalnız HTML almak için); doğrulanmış, başlık isteyen bir uç nokta bulunamadı.
**Dönen yapıdan bölüm alanları:** `chapterNode_up_to.data.dname="Chapter 50"`, `data.path="/chapter/bbgd24j"`, `data.datePublic=1707090254577`; ayrıca `chaNums_count=50`.
**Bölüm listesi için gereken id:** URL'deki başlık id'si: `/title/dgoz5m` → `dgoz5m`.
**Öneri:** Ayrıştırıcı yalnız gömülü Qwik state'indeki `chapterNode(_up_to).data` düğümlerini okuyabilir; 50 bölümün tamamı HTML'de olmadığı için (muhtemelen Qwik sunucu eylemiyle JS'te geliyor, doğrulanmadı) tam liste için render/tarayıcı ya da o eylemin tersine mühendisliği gerekir.
**Kanıt:** `chapterNode_up_to",5,[3,20,0,"bbgd24j",0,"data",5,[0,"dname",0,"Chapter 50",1,620,0,"/chapter/bbgd24j",0,"datePublic",0,1707090254577]]]]` | ölçüm: 95938 bayt, `datePublic`=1, `/chapter/` id=3, `chaNums_count`=50

---

## A3 — Manga Ball (mangaball.com) · bölümler boş

**Gömülü JSON:** Sayfa Next.js App Router; veri `self.__next_f.push(...)` içindeki RSC flight metninde (3 parça). Detay nesnesinde `initialChapters` dizisi var ama yalnız 20 bölüm (ilk kayıt `Capitulo 86.1`). Aynı nesnede `chapters_count: 253`, `latest_chapter_number: 86.1`. Ham HTML'de `<a href>` yok; linkler kaçışlı JSON içinde (`\"url\":\"https://www.leercapitulo.co/...\"`), HTML ayrıştırıcısı bu yüzden görmüyor. Yol: `self.__next_f` → detay nesnesi → `initialChapters`.

**API uç noktası:** `GET https://mangaball.com/api/v1/title/chapter-listing` — tam liste buradan gelir (istemci JS'te `get("/title/chapter-listing",{params:o})`, taban `/api/v1`).
Sorgu: `title_id=68516a86702284f83417c943&page=1&limit=20&group_by=flat&sort_order=desc&language=all&search=&user_id=`
Denendi: HTTP 200, `{"status":"success","code":200,"data":[...]}`. `user_id` boş gönderildi, çalıştı; ayrı auth/çerez gerekmedi.

**Yöntem-başlık:** GET; `-e "https://mangaball.com/"`, masaüstü Chrome 124 UA. Özel `Content-Type` gerekmedi.

**Dönen yapıdan bölüm alanları:** `data[]` içinde `id`, `title_id`, `lang` ("es"), `name` ("Capitulo 86.1"), `number` (86.1), `chapter_number`, `volume`, `url` (harici bölüm linki), `site` ("leercapitulo"), `created_at`, `updated_at`, `group.name`/`group_name` ("Tauros"), `views_count`. Üst düzeyde `pagination{page,limit,total,total_pages}`, `grouped_data`, `available_languages`, `liked_chapter_ids`.

**Gereken id:** `68516a86702284f83417c943` — adresteki 24 haneli hex kısım. Sayfadaki `titleId` alanı `68516a86702284f83417c943-childhood-friend-complex` biçiminde de geçiyor; API'ye sade hex verilmeli.

**Öneri:** Bölüm adımında `initialChapters` yetmez (20/253). API'yi `page`/`total_pages` ile döngüde çağırıp tümünü topla; her bölümün okuma adresi `url` alanındaki harici sitede. Alternatif iç yol `/chapter-detail/<id>` (JS'te görüldü, ayrıca test EDİLMEDİ).

**Kanıt:** `curl ... "/api/v1/title/chapter-listing?title_id=68516a86702284f83417c943&page=1&limit=3&..."` → `HTTP 200`, gövde `{"status":"success","code":200,"data":[{"name":"Capitulo 86.1","number":86.1,...}]}`. Detay sayfası: `HTTP 200`, 268102 bayt; `grep -o '__NEXT_DATA__\|self.__next_f\|__NUXT__'` → `3 self.__next_f`; `initialChapters` → 1 dizi, 20 `title_id` kaydı.

---

## A4 — WebtoonOku (webtoonoku.org) + Slept Manga (sleptmanga.com.tr) · bölümler boş, kapak yok

### WebtoonOku (webtoonoku.org)
**Gömülü JSON / API:** Yok — WordPress + LiteSpeed; bölümler sunucu HTML'inde `div#chapterList.chapter-grid` içinde. Tek AJAX `admin-ajax.php` (`flavor_history_*`, yalnız geçmiş); bölüm listesi AJAX'ı yok.
**Bölüm alanları:** `a.chapter-box[data-chapter]` (sayı), `span.chapter-num` ("Ch 50"), `span.chapter-views`, `span.chapter-date[data-time-ts]`; 50 tekil bölüm linki var.
**Kapak kaynağı (liste):** `img.attachment-manga-thumb.wp-post-image` → URL `data-src` içinde; `src` base64 SVG yer tutucu. Detayda `img.manga-cover-img` aynı. **data-src yeterli.** Uyarı: `img.type-badge-img` rozeti de var.

### Slept Manga (sleptmanga.com.tr)
**Gömülü JSON / API:** Next.js App Router; detay HTML'inde tek `self.__next_f.push` RSC yükü, kaçışlı `\"chaptersCount\":1,\"chapters\":[{...}]`.
**Bölüm alanları:** `_id`, `number`, `chapterTitle`, `createdAt`, `updatedAt`, `views`, `premium`, `earlyAccess`, `earlyAccessEnd`, `coinPrice`, `locked`, `purchased`.
**Bölüm linki biçimi:** `/manga/{slug}/{number}` (ör. `/manga/monster/0`), 3 parça, son parça sayı — motorun kuralına uyar.
**Kapak kaynağı (liste):** `img[data-nimg=fill]` `src`/`srcSet` = `/api/image-proxy?url=<cdn URL enc>&w=…&q=75&f=webp`; bazı kapaklar doğrudan dış URL (`r.resimlink.com`).
**403 alan kapak:** `/api/image-proxy` → `{"success":false,"error":"API Access Denied. Use the official website or app."}` (403). Ham `cdn.sleptmanga.com.tr/covers/monster.webp` Referer'sız 403, `Referer: https://sleptmanga.com.tr/` ile 200 → `url` parametresini çözüp CDN'e Referer'lı git.

### Kanıt
WebtoonOku: `<a href="https://webtoonoku.org/hapci-prens-chapter-50/" class="chapter-box" data-chapter="50"><span class="chapter-num">Ch 50</span>…` (50 tekil link)
Slept: `chaptersCount\":1,\"chapters\":[{\"_id\":\"66d194c9be84138125668408\",\"number\":0,...}]`
403: `{"success":false,"error":"API Access Denied. Use the official website or app."}`

---

## A5 — Koreli Scans (nabicix.com) + Lunar Manga (lunarx.to) · bölümler boş, kapak yok, Lunar arama boş

### Koreli Scans (nabicix.com)
**Liste kart linki:** `https://www.nabicix.com/manga/<slug>/` — 2 parça, `/manga/` ön eki (ör. `<a href="https://www.nabicix.com/manga/akademinin-basrol-oyuncusu/" title="Akademinin Başrol Oyuncusu">`). Liste HTML'inde `/manga/feed/` ve `/manga/list-mode` de link olarak var, süzülmeli. `nabicix.com/manga` → 301 → `https://www.nabicix.com/manga/`.
**Bölüm kaynağı:** Detay HTML'inde düz `<a href>`; biçim `https://www.nabicix.com/<slug>-bolum-<N>/` — TEK yol parçası (`/manga/` yok). Örnek sayfada 140 benzersiz bölüm linki. `wp-manga-chapter` / `chapter-item` sınıfı YOK (grep 0). Ayrıştırıcı ≥3 parça istediği için hepsi eleniyor = "bölümler boş". Detay `<slug>` slash'sız 301 döner, `-L` olmadan gövde BOŞ; `<slug>/` veya `-L` şart.
**Kapak kaynağı:** `data-src="https://image.nabicix.com/2026/09/Akademinin-Basrol-Oyuncusu.webp"`; `src` base64 SVG placeholder. → **data-src yeterli**.
### Lunar Manga (lunarx.to)
**Liste kart linki:** `/manga/<slug>` (ör. `/manga/quiet-in-the-office`). HTML'de `<a href>` YOK; Next.js `self.__next_f` RSC yükünde `\"siteUrl\":\"/manga/<slug>\"`. Liste sayfasında `<img>` de yok.
**Bölüm kaynağı:** Gömülü RSC JSON: `\"chapters\":[{\"chapter\":\"1\",\"chapter_number\":1,\"chapter_title\":\"Chapter 1\",...}]`; bölüm objesinde URL alanı yok. Okuyucu yolu istemci JS'inde kuruluyor: `` `/manga/${slug}/${chapterNumber}?lang=${code}` `` (chunk `0brn8ds4udkgg.js`). HTML'de bölüm linki/`chapter-item` yok → parser 0 bulur.
**Kapak kaynağı:** RSC JSON `\"coverImage\":{\"large\":\"https://vault.lunarx.to/cdn/admin/manga/migrated/<uuid>.png\"}`; detayda `\"cover_url\"` aynı CDN. HTML `<img>` yok → JSON alanı okunmalı.
**Arama:** gözlenen adres `/manga/search` (liste sayfasında `<a href="/manga/search">`); giriş placeholder'ı "Search for manga... (e.g., Berserk)". `?q=` HTML'de gözlenmedi, sonuç istemci tarafında → sorgu parametresi BULUNAMADI.
### Kanıt
- Koreli: `<a href="https://www.nabicix.com/manga/akademinin-basrol-oyuncusu/" title="Akademinin Başrol Oyuncusu">` · `href="https://www.nabicix.com/akademinin-basrol-oyuncusu-bolum-1/"`
- Lunar: `\"siteUrl\":\"/manga/quiet-in-the-office\"` · `\"chapters\":[{\"chapter\":\"1\",\"chapter_number\":1,...` · `` `/manga/${e}/${aP.chapterNumber}?lang=${rJ}${t}` ``

---

## A6 — Nyx Scans (nyxscans.com) sayfa boş + Sunset Manga (sunsetscans.com.tr) sayfa boş + Rüya Manga (ruyamanga2.com) arama boş + Amanga Planet (amangaplanet.com.tr) sayfa 403

### Nyx Scans — sayfa
**Bölüm linki:** `https://nyxscans.com/series/can-i-cry-now/chapter-66` **Görsel kaynağı:** HTML, `media.nyxscans.com` **Desen:** `<img src="https://media.nyxscans.com/upload/series/<slug>/<hash>/page-0001_01_<ts>-<id>.webp" data-reader-page-image="true" alt="… Page 1">`
Not: `a-king-is-born-on-the-road-novel` bölümü roman; görseli yok, ilk testte boş çıkması bundan. Çizgi roman bölümünde 51 tekil görsel URL'si var → HTML yeterli, ayrıştırıcı deseni yanlış (`data-reader-page-image` veya alt "Page N" ile seçilmeli).
### Sunset Manga — sayfa
**Bölüm linki:** `https://sunsetscans.com.tr/manga/angel-kiss/1-bolum/` **Görsel kaynağı:** HTML'de `src` YOK; `<div data-token="=HwAjxGB1…" data-index="0" data-alt="Angel Kiss 1. Bölüm - Sayfa 1">` **Desen:** `toon-reader.js` içindeki `deriveTon2SessionKey` + `decryptPayloadBuffer` şifreli yükü çözüyor; çerçeve CDN tabanı `https://b-cdn.sunsetscans.com.tr/frames/`. Görseller yalnız JS içinde; tam şifre çözme yolu BULUNAMADI.
### Rüya Manga — arama
**Çalışan arama adresi:** `POST https://www.ruyamanga2.com/wp-admin/admin-ajax.php?action=wp-manga-search-manga`, gövde `title=one` → `{"success":true,"data":[{"title":"Bones","url":"…/manga/bones/","type":"manga"},…]}` **Dönen manga linki sayısı:** en az 4 (yanıt 500 baytta kesildi, `success:true`). GET `?s=a`, `?s=one`, `?s=a&post_type=manga` → 0 manga linki; `?q=` yok sayılıyor (`?q=zzzqqqxxx` de aynı 18 seri).
### Amanga Planet — 403
**Görsel adresi:** `https://amangaplanet.link/wp-content/uploads/TR/TRA04/A04Bolum1-001.webp` (bölüm: `https://www.amangaplanet.com.tr/akademinin-dehasi-bolum-1/`) **Referer=site:** 200 **Referer=bölüm:** 200 — **eksik başlık: Referer** (Referer'sız 403; aynı yol `www.amangaplanet.com.tr` altında 404, çünkü sayfalar farklı hostta).
### Kanıt
Nyx: `<img src="https://media.nyxscans.com/upload/series/can-i-cry-now/1c5a5993-58fb-4e12-90c8-02ea3881e08c/page-0001_01_1793893156135-803506.webp" width="800" height="5000" alt="Can I Cry Now? Chapter 66 Page 1" data-reader-page-image="true">`
Sunset: `<div … data-token="=HwAjxGB1DGB3RQs8qGAjVQs8OaLyqaYj8lA5tGA4ZwL3pGM3tQBktGLyMGMyqwZxSGAlHJMkRQA28PMxMGA1RQBlDGAwSzAsS2MhSJoiVUqh02ow5lphS2LmEKMm5Jqm5voxAJYv9lY6ZUp0EUn" data-index="0" data-alt="Angel Kiss 1. Bölüm - Sayfa 1">` · `const cdnFramesBase = 'https://b-cdn.sunsetscans.com.tr/frames/'`
Rüya: `{"success":true,"data":[{"title":"Bones","url":"https:\/\/www.ruyamanga2.com\/manga\/bones\/","type":"manga"},{"title":"Baş Kötünün Kızgınlık Dönemi",…}]}` · `?q=zzzqqqxxx` → 18 tekil seri (parametre yok sayılıyor)
Amanga: `referer=site: 200` · `referer=chapter: 200` · `no-referer: 403` · `www-host: 404` · `Server: cloudflare`

---

## Karar (ana oturum doldurur)

_(boş)_
