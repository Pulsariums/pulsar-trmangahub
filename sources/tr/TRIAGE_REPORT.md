# TR kaynaklari - kademeli test ve onarim raporu

Bu rapor `scripts/triage.py` -> `test_stage1.py` -> `test_stage2.py` -> `repair_stage3.mjs` zincirinin ciktisidir. Her asama, oncekini gecemeyenlere uygulanir; `saglikli` olanlar liste+bolum+gorsel zincirini gercekten gecmistir (sadece liste sayfasinda motor markeri bulunmasi yeterli sayilmaz).

## Ozet

| Durum | Adet | Aciklama |
|---|---|---|
| yerelden-dogrulanamadi | 88 | bu makineden/agdan domaine hic baglanilamadi (CI'da farkli IP ile dogrulanmali) |
| saglikli | 27 | liste -> detay -> bolum -> gorsel zinciri gercekten calisti |
| manuel-inceleme | 21 | upstream/override parser kirik; otomatik kod yamasi guvenilir degil |
| kullanici-dogruladi-test-yanlis-negatif | 12 | kullanici Kototoro'da elle calistigini dogruladi; otomatik test heuristigi bu site yapisina uymadi (YANLIS-NEGATIF, kaynak kirik degil) |
| kullanici-dogruladi-yerelden-erisilemedi | 10 | kullanici elle calistigini dogruladi; bu makineden erisim engellendigi icin otomatik test calisamadi |
| test-edilemedi | 9 | zincirin bir adiminda site HTTP hatasi/baglanti sorunu verdi |
| onarilamadi | 3 | selector kirik, otomatik onarim denendi ama basarisiz (manuel bakilmali) |
| onarildi | 1 | selector kirikti, otomatik yeniden uretim + statik HTML dogrulamasiyla onarildi |

## Onarilan kaynaklar

| Domain | Detay |
|---|---|
| ragnarscans.net | parser yeniden uretildi ve statik HTML ile dogrulandi |

## Manuel inceleme gereken kaynaklar

Upstream/override parser'lar: base-class parametreli yapidan dolayi otomatik selector yamasi guvenilir degil, elle bakilmali.

| Domain | Motor | Detay |
|---|---|---|
| adumanga.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| araznovel.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| asemifansub.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| athenamanga.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| esomanga.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| fuchscans.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| garciamanga.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| hoifansub.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| manga.araznovel.com | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| mangabahcesi.com | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| mangadusleri.mom | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| mangakusu.com | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| mangasiginagi.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| mugimanga.com | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| nyxmanga.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| okutoon.com | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| paradoxscans.com | - | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| piedpiperfansub.me | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| piedpiperfansubyy.me | madara | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| seraphmanga.com | mangareader | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |
| shadowceviri.blogspot.com | zeistmanga | upstream/override parser: otomatik selector yamasi guvenilir degil, manuel inceleme gerekli |

## Hala kirik (onarilamadi veya test edilemedi)

| Domain | Motor | Durum | Detay |
|---|---|---|---|
| alucardscans.com | signedrest | test-edilemedi | liste sayfasi cekilemedi: http 525 |
| amangaplanet.com.tr | mangathemesia | onarilamadi | genparser basarisiz: Error: Command failed: node scripts/genparser.mjs "recon-out/amangaplanet.com.t |
| manga-tr.com | - | test-edilemedi | liste sayfasi cekilemedi: http 403 |
| mangagezgini.online | madara | test-edilemedi | liste sayfasi cekilemedi: http 403 |
| mangazure.net | - | test-edilemedi | liste sayfasi cekilemedi: http 523 |
| manwe.pro | madara | test-edilemedi | liste sayfasi cekilemedi: http 456 |
| millascan.com | madara | onarilamadi | genparser basarisiz: Error: Command failed: node scripts/genparser.mjs "recon-out/millascan.com.spec |
| nirvanamanga.com | mangareader | test-edilemedi | liste sayfasi cekilemedi: http 500 |
| opiatoon.shop | madara | onarilamadi | genparser basarisiz: Error: Command failed: node scripts/genparser.mjs "recon-out/opiatoon.shop.spec |
| raindropteamfan.com | mangareader | test-edilemedi | liste sayfasi cekilemedi: ConnectionError: ('Connection aborted.', ConnectionResetError(10054, 'Varo |
| ruyamanga.net | madara | test-edilemedi | liste sayfasi cekilemedi: http 523 |
| sadscans.com | custom | test-edilemedi | liste sayfasi cekilemedi: http 403 |

## Yerelden dogrulanamayan (CI'da kontrol edilmeli)

88 domain bu makineden/agdan hic erisilemedi (SSL/baglanti reddi - site tarafi degil, yerel ag kisitlamasi olasi). `gh workflow run _test.yml` ile CI'da gercek sonuc alinmali.

## Kullanici tarafindan dogrulanan ama otomatik testin yanildigi kaynaklar

Bu domainler `sources/tr/verified_working_kototoro_export.json` (kullanicinin Kototoro'dan elle test edip export ettigi grup) icinde yer alir - kullanici gercekten calistigini dogruladi. Otomatik test bunlari 'fail'/'unverified_local' derse, bu testin kendi heuristiginin (link bulma, yerel ag erisimi) yetersizligidir, kaynagin kendisi degil.

**Test yanlis-negatif uretti (site erisilebilir ama heuristik link/selector bulamadi):**

| Domain | Motor |
|---|---|
| diamondfansub.com | madara |
| mangacix.net | mangareader |
| mangadenizi.net | mmrcms |
| mangadiyari.com | - |
| mangawt.com | madara |
| merlintoon.com | mangareader |
| mikrokosmosfb.blogspot.com | zeistmanga |
| nabicix.com | madara |
| patimanga.com | mangareader |
| ruyamanga2.com | madara |
| tenshimanga.com | custom |
| webtoonoku.org | - |

**Yerelden hic erisilemedi (CI'da dogrulanmali, test heuristigiyle alakasiz):**

| Domain | Motor |
|---|---|
| golgebahcesi.com | mangareader |
| juratempe.st | - |
| korelimanga.com | initmanga |
| kuroimanga.site | - |
| tilkiscans.com | madara |
| toontaku.com | - |
| tuhafscans.com | madara |
| uzaymanga.com | custom |
| webtoonhatti.club | madara |
| yaoiflix.fit | madara |

