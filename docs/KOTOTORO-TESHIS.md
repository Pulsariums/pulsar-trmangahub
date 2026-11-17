# Kototoro: kaynak listesinde kaynakların kaybolması — teşhis

Tarih: 2026-11-17 · Salt okunur inceleme (Kototoro'ya dokunulmadı)

## Özet

Kaynak sekmesi, NSFW gizleme ayarı **kaynak listesine de** uygulandığı için bazı kaynakları gösterimden düşürüyor. Paket kartındaki sayı eklentinin oluşturduğu kaynak sayısını gösterdiği için "5/5 aktif" yazıyor; liste ise süzgeçten geçtiği için 1 gösteriyor.

## Sebep (kanıt)

- `org.skepsun.kototoro.desktop.app.DesktopAppKt.DesktopSourcePane` (masaüstü ızgarası `DesktopSourceGridKt.DesktopSourceGrid`) kaynak listesini şu koşulla süzüyor:
  `settings.hidesNsfw(DesktopNsfwTarget.SOURCES) && DesktopSourceSettingsKt.isNsfwSource(listing, overrides)`
  Kanıt: `javap -p -c` → `DesktopAppKt` bytecode 429-449 (`getstatic DesktopNsfwTarget.SOURCES`, `hidesNsfw`, `isNsfwSource`, `ifne`).
- `DesktopSourceSettingsKt.isNsfwSource` (bytecode 12-49): önce `SourceNsfwOverrideSet.resolve(name)` uygulanır (`sfw` seti → false, `nsfw` seti → true); override yoksa `SourceRef.contentType.startsWith("HENTAI_")`.
- `MihonJarRegistry` (bytecode 915-933): Mihon eklentisi için `MihonJarMetadata.isNsfw()` true ise `SourceRef.contentType` değeri `"HENTAI_" + contentType` yapılıyor. Bu bayrak **kaynak düzeyinde değil, paket/jar düzeyinde**.
- `DesktopSourceSettings.hidesNsfw` (bytecode 8-12): yalnız `nsfwTargets.contains(SOURCES)` kontrolü.

Jar'lar: `C:\Users\pulsa\Desktop\Kototoro\app\desktop-app-fede33141166766b43ce2cea7069ecc.jar`, `desktop-runtime-9c16aaca3b8e1d5dfcfd2b59566a35c.jar`, `source-host-3da19ed4277c91484caf7946d19699c5.jar`.

## Neden yalnız "NSFW" kaynaklar

Ölçülen veri (eklenti tarafı):

| Kaynak | asset nsfw | Test paketinde göründü |
|---|---|---|
| OkuToon | 0 | evet |
| Averis Fansub | 1 | hayır |
| Luna Scans (tuhafscans.com) | 1 | hayır |
| Outcats Scans | 1 | hayır |
| TonizuToon | 1 | hayır |

4/4 korelasyon: gizlenenlerin tamamı NSFW işaretli, görünen tek kaynak NSFW değil. Aynı kalıp 18+ paketlerinde de var (TR 18+ 7→5, Global 18+ 25→21).

Eklenti tarafında kaynak düşüren bir kapı **yok**: `deadSources`/`deadHosts` eşleşmesi 0, `PulsarData.allowed` listesi indeksle birebir, yerel harness test/tr18 APK'larında 5/5 kaynak oluşturdu.

## Çözüm

### Kototoro tarafı (kalıcı)

`DesktopSourcePane` / `DesktopSourceGrid` içindeki `hidesNsfw(DesktopNsfwTarget.SOURCES)` koşulu kaynak listesinden kaldırılsın; NSFW gizleme keşfet/akış/favori ekranlarında kalsın, kaynak listesinde yalnızca rozet gösterilsin. Alternatif: `sources_nsfw_targets` varsayılanı boş olsun.

### Kullanıcı tarafı (şimdi)

1. Kototoro → Ayarlar → Kaynaklar → NSFW hedeflerinde **"Sources" kapalı** olsun.
   Bu yapılırsa test grubundaki 5 kaynak da görünür (18+ paketlerindeki eksikler dahil).
2. Alternatif: gizlenmesi istenmeyen kaynakları `source_sfw_overrides` listesine ekle.

### Eklenti tarafı

Tek başına çözüm yok: `MihonJarMetadata` paket düzeyinde olduğu için `PulsarSource`'a kaynak başına `contentType` eklemek Kototoro'nun Mihon yolunda işe yaramıyor. Görünürlük şart ise 18+ kaynaklar SFW görünen ayrı bir pakete alınmalı — içerik etiketi açısından yanlış olduğu için önerilmez.

## Doğrulama adımı

Kototoro'da "Sources" NSFW hedefi kapatıldıktan sonra test paketinde 5 kaynak görünmeli; TR 18+ 7, Global 18+ 25 olmalı. Görünmüyorsa süzgeç dışında ikinci bir kapı var demektir.

## Güven

Yüksek: süzgeç sınıf/metot ve bytecode düzeyinde kanıtlı. Zayıf nokta: `sources_nsfw_targets` değeri diskteki tercih dosyalarında bulunamadı; "SOURCES hedefi etkin" sonucu gözlenen gizleme davranışından çıkarıldı.
