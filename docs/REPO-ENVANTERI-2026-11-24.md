# Depo envanteri + Mihon tamamlama — 2026-11-24

Kaynak: Kototoro → Extension management → **Repositories (65)**, 8 ekran görüntüsü.
Ekranlarda **47 tekil kayıt** görünüyor (65'in geri kalanı görüntülenmedi).
Makine okunur hâli: `pulsar-v2/data/repo-envanteri-2026-11-24.json`.

`installed` = Refresh/Sil butonu var, `available` = Ekle butonu var.

## Özet

| Tür | Kayıt | Ekli | Yeni |
|---|---:|---:|---:|
| TVBox | 29 | 0 | 29 |
| Mihon | 3 | 2 | 1 |
| Aniyomi | 3 | 2 | 1 |
| CloudStream | 5 | 0 | 5 |
| LNReader | 3 | 3 | 0 |
| IReader | 3 | 3 | 0 |
| Legado | 1 | 0 | 1 |
| **Toplam** | **47** | **10** | **37** |

Ekosistem notu: TVBox / LNReader / IReader / Legado ayrı uygulama formatları —
Kototoro/Mihon/Aniyomi bunları tüketmez. Bizim tarafa doğrudan girenler:
**Mihon (3), Aniyomi (3), CloudStream (5)**.

## Mihon — 2026-11-24 doğrulaması

| Depo | repo.json | index | Kayıt | Durum |
|---|---|---|---:|---|
| **Keiyoushi** | `.../keiyoushi/extensions/repo/repo.json` | **`index_v2` → `index.pb` (protobuf, 126 KB)** | — (v2) | Canlı. `index.min.json` artık yalnız "Outdated App" / "Update to Mihon 0.20.1+" uyarı kayıtları (2 stub). |
| **Yūzōnō** | `.../yuzono/manga-repo/repo/repo.json` | `index_v2` yok → `index.min.json` | 2 (stub) | Canlı ama index'i Keiyoushi stub'ını aynalıyor. |
| **CopyManga Copy20** (TheNano) | `.../LittleSurvival/copymanga-copy20/repo/repo.json` | `index.min.json` | **5** | Canlı; APK 200. Kaynaklar: CopyManga 1.6.87, VomicMHPlus, BaoziManhuaPlus, ManwaYuPlus, HipManga. |
| KirouGC / Mihon-Variety | var | `index.min.json` | 2 | Canlı, küçük. |
| tachiyomiorg/extensions | yok | `index.min.json` | 4 | Arşiv (Kavita vb. eski). |
| Kohi-den, komikku-app, nana-xd, Secozzi, mihonapp, KudoAni (Aniyomi) | — | 404 | — | Ölü/taşınmış. |

### Mihon'u "tamamlamak" için iki yol
**A) Uygulamaya depo ekle (dakikalar).** Eksik olan tek canlı Mihon deposu
**CopyManga Copy20** (5 kaynak). Adres:
`https://raw.githubusercontent.com/LittleSurvival/copymanga-copy20/repo/index.min.json`
Keiyoushi ve Yūzōnō zaten ekli. KudoAni (Aniyomi) ölü → listeden kaldırılabilir.

**B) Tek çatıda birleştir (mega repo).** Mihon'da `apk` alanı **dosya adı** olduğu
için aynalama mümkün: APK'lar indirilip `apk/` altına konur, indeks birleştirilir.
Engel: Keiyoushi `index.min.json`'u stub; gerçek liste **protobuf `index.pb`**.
Birleştirme için:
1. `index.pb` çözücü (schema) + APK aynalama (Keiyoushi ~bin eklenti, yüzlerce MB),
2. ya da Keiyoushi'yi birleştirmeden yalnız Copy20 + KirouGC'yi kendi indeksimize katmak.

Bizim repolar (`pulsar-v2/repo`, `pulsar-video/repo`) `index_v2: null` yayınlıyor;
Kototoro `index.min.json`'a düşüyor — v2 geçişi bizim tarafta zorunlu değil.

## Ekranlardaki tam liste

### TVBox (29)

| Ad | URL |
|---|---|
| 非凡资源网 | `http://api.ffzyapi.com/api.php/provide/vod/at/xml/` |
| 魔都动漫资源 | `https://www.mdzyapi.com/api.php/provide/vod/at/xml/` |
| 黑料资源网 | `https://www.heiliaozyapi.com/api.php/provide/vod/at/sexml/` |
| 豪华资源网 | `https://hhzyapi.com/api.php/provide/vod` |
| 速播资源 | `https://subocj.com/api.php/provide/vod` |
| 量子资源 | `https://cj.lziapi.com/api.php/provide/vod` |
| 金鹰资源 | `https://jyzyapi.com/provide/vod/from/jinyingm3u8/at/xml/` |
| 闪电资源 | `https://sdzyapi.com/api.php/provide/vod` |
| 快车资源采集站 | `https://caiji.kuaichezy.org/api.php/provide/vod` |
| 新浪资源 | `https://api.xinlangapi.com/xinlangapi.php/provide/vod/at/xml` |
| 无尽资源 | `https://api.wujinapi.me/api.php/provide/vod` |
| 暴风资源 | `https://bfzyapi.com/api.php/provide/vod` |
| 极速资源网 | `https://jszyapi.com/api.php/provide/vod` |
| 玉兔资源 | `https://apiyutu.com/api.php/provide/vod/at/xml/` |
| 电影天堂资源 | `http://caiji.dyttzyapi.com/api.php/provide/vod/at/xml/` |
| 索尼资源 | `https://suoniapi.com/api.php/provide/vod` |
| 红牛资源采集站 | `https://www.hongniuzy2.com/api.php/provide/vod` |
| 虎牙资源 | `https://www.huyaapi.com/api.php/provide/vod/at/xml/` |
| 西瓜资源 | `https://caiji.xgzyapi.com/api.php/provide/vod/at/xml/` |
| 豆瓣资源 | `https://caiji.dbzy5.com/api.php/provide/vod` |
| 360 资源站 | `https://360zyzz.com/api.php/provide/vod` |
| ikun 资源网 | `https://ikunzyapi.com/api.php/provide/vod` |
| Qiqi TVBox | `http://z.qiqiv.cn/123.txt` |
| 光速影视资源网 | `https://api.guangsuapi.com/api.php/provide/vod/at/xml/` |
| 天涯资源 | `https://tyyszy.com/api.php/provide/vod` |
| 奥斯卡资源 | `https://aosikazy.com/api.php/provide/vod/at/xml/` |
| 奶香香资源站 | `https://naixxzy.com/api.php/provide/vod/at/xml/` |
| 如意资源网 | `https://cj.rycjapi.com/api.php/provide/vod/at/xml/` |
| 影剧资源网 | `https://caiji.maotaizy.cc/api.php/provide/vod/at/xml/` |

### Mihon / Aniyomi / CloudStream (11)

| Ad | Tür | URL | Durum |
|---|---|---|---|
| Yüzönö | Mihon | `https://raw.githubusercontent.com/yuzono/manga-repo/repo/index.min.json` | ekli |
| CopyManga Copy20 | Mihon | `https://raw.githubusercontent.com/LittleSurvival/copymanga-copy20/repo/index.min.json` | **yeni** |
| Keiyoushi | Mihon | `https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.min.json` | ekli |
| Official Aniyomi extensions | Aniyomi | `https://raw.githubusercontent.com/aniyomiorg/aniyomi-extensions/repo/index.min.json` | ekli |
| Yüzönö | Aniyomi | `https://raw.githubusercontent.com/yuzono/anime-repo/repo/index.min.json` | ekli |
| KudoAni | Aniyomi | `https://raw.githubusercontent.com/KudoAni/aniyomi-extensions/repo/index.min.json` | ölü (404) |
| Redowan's BDIK repository | Cloudstream | `https://raw.githubusercontent.com/redowan99/Redowan-CloudStream/mas…` | yeni |
| SkillShare-Repo | Cloudstream | `https://raw.githubusercontent.com/techtanic/SkillShare-Repo/builds/repo.j…` | yeni |
| Turkish Providers Repository | Cloudstream | `https://raw.githubusercontent.com/keyiflerolsun/Kekik-cloudstream/maste…` | yeni |
| Vietnamese Extension | Cloudstream | `https://gitlab.com/tearrs/cloudstream-vietnamese/-/raw/main/repo.json` | yeni |
| zzikozz | Cloudstream | `https://codeberg.org/zzikozz/frencharchive/raw/branch/Release/repo.json` | yeni |

### LNReader / IReader / Legado (7)

| Ad | Tür | URL | Durum |
|---|---|---|---|
| github.com / plugins | LNReader | `https://github.com/lnreader/lnreader-plugins/tree/master/plugins` | ekli |
| raw… / index.json | LNReader | `https://raw.githubusercontent.com/lnreader/lnreader-plugins/main/index.js…` | ekli |
| raw… / plugins.min.json | LNReader | `https://raw.githubusercontent.com/LNReader/lnreader-plugins/plugins/v3.…` | ekli |
| Inreader/lnreader-plugins | IReader | `https://raw.githubusercontent.com/lnreader/lnreader-plugins/main/index.js…` | ekli |
| url (çöp kayıt) | IReader | `https://www.google.com/url/index.min.json` | ekli |
| IReaderorg/IReader-extensions | IReader | `https://raw.githubusercontent.com/IReaderorg/IReader-extensions/repov2/…` | ekli |
| XIU2 Yuedu | Legado | `https://cdn.jsdmirror.com/gh/XIU2/Yuedu/shuyuan` | yeni |

## CopyManga Copy20 hasadı (2026-11-24)

Mihon listesindeki tek canlı eksik depo (**TheNano / Copy20**, 5 eklenti, APK'lar 200) indirildi,
JAR'a çevrildi ve kaynakları tek tek ölçüldü. Arşiv: `.work/arsiv/mihon/copy20/` (git dışı).
Provenance + sha256: `pulsar-v2/data/arsiv-mihon-copy20.json`.

| Eklenti | Site | Ölçüm | Sonuç |
|---|---|---|---|
| 拷贝漫画 | copy3000.com | liste kapaksız; bölüm HTML'inde görsel yok; API HTTP 210 anti-piracy kilidi | **dönüştürülemez** |
| vomic漫+ | vomicmh.com | okuyucu giriş istiyor (RSC isLogin:false, getChapterInfo 401) | **dönüştürülemez** |
| 包子漫画+ | tw.webmota.com | liste 108 kart; bölüm listesi Nuxt istemci tarafı, uç yok | **dönüştürülemez** |
| **漫蛙2+** | manwari.cc → **manwauu.cc** | liste 60 / bölüm 30 / okuyucu JSON `/api/comic/image/{chapterId}` → `data.images[].url` (200 image/jpeg 305 KB) | **dönüştürüldü** |
| 嬉皮漫畫 | m.hipmh.com | liste 36 kart; bölüm API'de; okuyucu sayfaları istemcide üretiliyor | **dönüştürülemez** |

Dönüştürülen tek kaynak `manwauu.cc` adıyla kataloğa eklendi (nsfw=1). Test paketinde
harness ile doğrulanıp global18'e terfi ettirilecek; geçmezse `failed` işaretlenecek.

Kural: Mihon eklentisi HTML/JSON ile config'e çevrilebiliyorsa alınır; istemci tarafı JS,
giriş kilidi veya imzalı API varsa **parser yazılmadıkça** alınmaz (uydurma seçici yazılmaz).
