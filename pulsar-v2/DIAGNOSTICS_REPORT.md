# Pulsar-V2 Kaynak Teşhis ve Otomatik Tamirat Raporu

**Tarih:** 2026-10-16 10:45:30 UTC
**Toplam İncelenen Kaynak:** 181
**Canlı / Yayına Uygun:** 109
**Otomatik Onarılan:** 7
**Ölü / Elenen:** 72

## Teşhis Dağılımı

| Durum Kodu | Adet | Anlamı ve Çözüm |
|---|---|---|
| `CANLI_DOGRU` | 96 | Doğrudan açık ve sorunsuz çalışan kaynaklar. |
| `OTOMATIK_TAMIR_YONLENDIRME` | 5 | Site yeni domaine taşınmış, sistem otomatik tespit edip onardı. |
| `OTOMATIK_TAMIR_ALTERNATIF` | 2 | Ana domain ölmüş, ama yedek/alternatif domain canlı bulunup otomatik onarıldı. |
| `CLOUDFLARE_KORUMALI` | 6 | Cloudflare koruması aktif. Mihon içinde 'WebView ile Aç' ile sorunsuz açılır. |
| `YEREL_AG_ISP_ENGELI` | 44 | Türkiye yerel servis sağlayıcı/ağ engeli. CI sunucusunda doğrulanmalı. |
| `OLU_DNS_KAYDI_YOK` | 23 | Domain süresi dolmuş veya silinmiş (kurtarılamaz ölü). |
| `OLU_HTTP_SUNUCU_KAPALI` | 1 | Sunucu HTTP 404/521/523 veriyor (site kapatılmış). |
| `DOGRULANMIS_KORUNAN` | 0 | Kullanıcı Kototoro'da doğruladığı için teste takılsa dahi korunanlar. |

## Otomatik Onarılan Kaynaklar

| Eski Domain | Yeni / Çalışan Domain | Onarım Sebebi |
|---|---|---|
| mangakusu.com | **ragnarscans.net** | Site mangakusu.com adresinden ragnarscans.net adresine taşınmış, otomatik onarıldı. |
| eleceedturkiye.com | **nabicix.com** | Site eleceedturkiye.com adresinden nabicix.com adresine taşınmış, otomatik onarıldı. |
| mangagezginim.com | **mangagezgini.online** | Eski domain (mangagezginim.com) DNS ölüydü, çalışan alternatif domain (mangagezgini.online) ile otomatik onarıldı. |
| mangaoku.info | **ww16.mangaoku.info** | Site mangaoku.info adresinden ww16.mangaoku.info adresine taşınmış, otomatik onarıldı. |
| opiatoon.art | **opiatoon.shop** | Eski domain (opiatoon.art) DNS ölüydü, çalışan alternatif domain (opiatoon.shop) ile otomatik onarıldı. |
| sunsetmanga.com | **sunsetscans.com.tr** | Site sunsetmanga.com adresinden sunsetscans.com.tr adresine taşınmış, otomatik onarıldı. |
| piedpiperfansub.me | **ww17.piedpiperfansub.me** | Site piedpiperfansub.me adresinden ww17.piedpiperfansub.me adresine taşınmış, otomatik onarıldı. |

## Neden Ölü? (Kurtarılamayan Sitelerin Analizi)

| Domain | Durum | Teşhis Detayı |
|---|---|---|
| 3hentai.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| adumanga.com | `OLU_SPAM_KUMAR_YONLENDIRME` | Domain süresi bitmiş, kumar/spam sitesine yönlendirilmiş (koplo77-irama.com). |
| adumanga.com | `OLU_SPAM_KUMAR_YONLENDIRME` | Domain süresi bitmiş, kumar/spam sitesine yönlendirilmiş (koplo77-irama.com). |
| akuma.moe | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| alucardscans.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| anisamanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| armoniscans.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| asemifansub.com | `OLU_SPAM_KUMAR_YONLENDIRME` | Domain süresi bitmiş, kumar/spam sitesine yönlendirilmiş (situsbet200resmi.org). |
| asurascans.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ayatoon.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| caprazmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| caprazmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| culturesubs.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| domalfansb.com.tr | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| epikman.ga | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ghostfansub.co | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ghostoon.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| guncelmanga.net | `OLU_SPAM_KUMAR_YONLENDIRME` | Domain süresi bitmiş, kumar/spam sitesine yönlendirilmiş (789betwin.cc). |
| hattorimanga.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| hayalistic.com.tr | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| hentaihand.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| holyscans.com.tr | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| imparatormanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| jellyring.co | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| kabusmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| kedi.to | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| kuroimanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| laviniafansub.site | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| lilyumfansub.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| manga-ay.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| manga-sehri.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| manga-sehri.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangabahcesi.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangabahcesi.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangacim.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangaefendisi.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangagezgini.site | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangakings.com.tr | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangakoleji.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangamillion.shueisha.co.jp | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangaoku.org | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangaokusana.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| mangaokutr.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| mangazure.net | `OLU_HTTP_SUNUCU_KAPALI` | Sunucu HTTP 523 dönüyor (Sayfa bulunamadı veya sunucu kapalı). |
| manwe.pro | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| monomanga.com.tr | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| moondaisyscans.biz | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| myreadingmanga.info | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| nabiscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| nhentai.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| nirvanamanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| niverafansub.org | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| prunusscans.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| ragnarscans.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| ruyamanga.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| sarcasmscans.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| siyahmelek.my | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| siyahmelek.org | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| snscoeurturkey.blogspot.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| strayfansub.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| tempestfansub.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| tempestscans.net | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| titanmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| trwebtoon.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| universe.leagueoflegends.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| viyafansub.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| webtoonhatti.me | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| yaoibar.gay | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| yaoimangaoku.net | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
| yaoitr.org | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| yetiskinruyamanga.com | `OLU_DNS_KAYDI_YOK` | DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş). |
| zamanmanga.com | `YEREL_AG_ISP_ENGELI` | Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edil |
