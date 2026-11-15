# Pulsar-V2 Kaynak Teşhis ve Otomatik Tamirat Raporu

**Tarih:** 2026-11-15 15:56:09 UTC
**Toplam İncelenen Kaynak:** 197
**Canlı / Yayına Uygun:** 154
**Otomatik Onarılan:** 28
**Ölü / Elenen:** 43

## Teşhis Dağılımı

| Durum Kodu | Adet | Anlamı ve Çözüm |
|---|---|---|
| `CANLI_DOGRU` | 107 | Doğrudan açık ve sorunsuz çalışan kaynaklar. |
| `OTOMATIK_TAMIR_YONLENDIRME` | 24 | Site yeni domaine taşınmış, sistem otomatik tespit edip onardı. |
| `OTOMATIK_TAMIR_ALTERNATIF` | 4 | Ana domain ölmüş, ama yedek/alternatif domain canlı bulunup otomatik onarıldı. |
| `CLOUDFLARE_KORUMALI` | 18 | Cloudflare koruması aktif. Mihon içinde 'WebView ile Aç' ile sorunsuz açılır. |
| `YEREL_AG_ISP_ENGELI` | 17 | Türkiye yerel servis sağlayıcı/ağ engeli. CI sunucusunda doğrulanmalı. |
| `OLU_DNS_KAYDI_YOK` | 25 | Domain süresi dolmuş veya silinmiş (kurtarılamaz ölü). |
| `OLU_HTTP_SUNUCU_KAPALI` | 1 | Sunucu HTTP 404/521/523 veriyor (site kapatılmış). |
| `DOGRULANMIS_KORUNAN` | 1 | Kullanıcı Kototoro'da doğruladığı için teste takılsa dahi korunanlar. |

## Otomatik Onarılan Kaynaklar

| Eski Domain | Yeni / Çalışan Domain | Onarım Sebebi |
|---|---|---|
| merlintoon.com | **merlintoon.net** | Site merlintoon.com adresinden merlintoon.net adresine taşınmış, otomatik onarıldı. |
| juratempe.st | **youtube.com** | Site juratempe.st adresinden youtube.com adresine taşınmış, otomatik onarıldı. |
| asemifansub.com | **quoterivers.com** | Site asemifansub.com adresinden quoterivers.com adresine taşınmış, otomatik onarıldı. |
| adumanga.com | **riddles-with-answers.com** | Site adumanga.com adresinden riddles-with-answers.com adresine taşınmış, otomatik onarıldı. |
| juratempe.st | **youtube.com** | Site juratempe.st adresinden youtube.com adresine taşınmış, otomatik onarıldı. |
| mangaoku.org | **mangaoku.com.tr** | Site mangaoku.org adresinden mangaoku.com.tr adresine taşınmış, otomatik onarıldı. |
| eleceedturkiye.com | **nabicix.com** | Site eleceedturkiye.com adresinden nabicix.com adresine taşınmış, otomatik onarıldı. |
| siyahmelek.org | **siyahmelek.fun** | Eski domain (siyahmelek.org) DNS ölüydü, çalışan alternatif domain (siyahmelek.fun) ile otomatik onarıldı. |
| domalfansb.com.tr | **cerdma.com** | Site domalfansb.com.tr adresinden cerdma.com adresine taşınmış, otomatik onarıldı. |
| mangagezgini.site | **ww38.mangagezgini.site** | Site mangagezgini.site adresinden ww38.mangagezgini.site adresine taşınmış, otomatik onarıldı. |
| mangakusu.com | **ragnarscans2.com** | Site mangakusu.com adresinden ragnarscans2.com adresine taşınmış, otomatik onarıldı. |
| mangagezginim.com | **mangagezgini.online** | Eski domain (mangagezginim.com) DNS ölüydü, çalışan alternatif domain (mangagezgini.online) ile otomatik onarıldı. |
| guncelmanga.net | **sonew.mycloudstudio.co.in** | Site guncelmanga.net adresinden sonew.mycloudstudio.co.in adresine taşınmış, otomatik onarıldı. |
| mangaruhu.com | **mangaruhu.net** | Site mangaruhu.com adresinden mangaruhu.net adresine taşınmış, otomatik onarıldı. |
| mangakoleji.com | **dropcatch.com** | Site mangakoleji.com adresinden dropcatch.com adresine taşınmış, otomatik onarıldı. |
| moondaisyscans.biz | **expireddomains.com** | Site moondaisyscans.biz adresinden expireddomains.com adresine taşınmış, otomatik onarıldı. |
| mangaoku.info | **ww16.mangaoku.info** | Site mangaoku.info adresinden ww16.mangaoku.info adresine taşınmış, otomatik onarıldı. |
| opiatoon.art | **opiatoon.shop** | Eski domain (opiatoon.art) DNS ölüydü, çalışan alternatif domain (opiatoon.shop) ile otomatik onarıldı. |
| ragnarscans.com | **ragnarscans2.com** | Site ragnarscans.com adresinden ragnarscans2.com adresine taşınmış, otomatik onarıldı. |
| ruyamanga.net | **ruyamanga2.com** | Eski domain (ruyamanga.net) DNS ölüydü, çalışan alternatif domain (ruyamanga2.com) ile otomatik onarıldı. |
| webtoonhatti.me | **letzfetzofdb.top** | Site webtoonhatti.me adresinden letzfetzofdb.top adresine taşınmış, otomatik onarıldı. |
| seraphmanga.com | **heffalumpa.com** | Site seraphmanga.com adresinden heffalumpa.com adresine taşınmış, otomatik onarıldı. |
| trwebtoon.com | **trmanga.com** | Site trwebtoon.com adresinden trmanga.com adresine taşınmış, otomatik onarıldı. |
| adumanga.com | **riddles-with-answers.com** | Site adumanga.com adresinden riddles-with-answers.com adresine taşınmış, otomatik onarıldı. |
| strayfansub.com | **ww38.strayfansub.com** | Site strayfansub.com adresinden ww38.strayfansub.com adresine taşınmış, otomatik onarıldı. |
| sunsetmanga.com | **sunsetscans.com.tr** | Site sunsetmanga.com adresinden sunsetscans.com.tr adresine taşınmış, otomatik onarıldı. |
| zamanmanga.com | **ww38.zamanmanga.com** | Site zamanmanga.com adresinden ww38.zamanmanga.com adresine taşınmış, otomatik onarıldı. |
| piedpiperfansub.me | **ww17.piedpiperfansub.me** | Site piedpiperfansub.me adresinden ww17.piedpiperfansub.me adresine taşınmış, otomatik onarıldı. |

## Neden Ölü? (Kurtarılamayan Sitelerin Analizi)

| Domain | Durum | Teşhis Detayı |
|---|---|---|
| alucardscans.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| anisamanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| armoniscans.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| asurascans.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ayatoon.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| caprazmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| caprazmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| culturesubs.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| epikman.ga | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| fuchscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ghostfansub.co | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| hayalistic.com.tr | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| imparatormanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| jellyring.co | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| jiangzaitoon.icu | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| kabusmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| kedi.to | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| lilyumfansub.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| manga-sehri.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| manga-sehri.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangacim.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangaefendisi.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangakings.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangamillion.shueisha.co.jp | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangaokutr.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangazure.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| manwe.pro | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| nabiscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| nirvanamanga.com | `OLU_HTTP_SUNUCU_KAPALI` | Sunucu HTTP 521 dönüyor (Sayfa bulunamadı veya sunucu kapalı). |
| nyxmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| prunusscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| sarcasmscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| summertoons.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| summertoons.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| tempestfansub.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| tempestscans.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| timenaight.org | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| toonhane.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| universe.leagueoflegends.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| viyafansub.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| yaoibar.gay | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| yaoitr.org | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| yetiskinruyamanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
