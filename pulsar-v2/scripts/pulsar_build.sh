#!/usr/bin/env bash
#
# Pulsar-V2 — Nyora porter örüntüsüyle kendi eklentimizi KENDİ verimizle derler.
# Kopya değil, örnek: geçici (throwaway) resmi Mihon checkout'u yalnız eklenti
# DERLEME API'si için kullanılır; uygulama asla derlenmez. Modülümüz oraya
# :pulsar-extension olarak bağlanır; imza anahtarı CI'da her derlemede üretilir
# ve parmak izi APK'dan OTOMATİK okunur (generate_repo.py).
#
# Kullanım:  pulsar_build.sh [flavor ...]
#            FLAVORS="tr,tr18,global,global18,test" pulsar_build.sh
# Değişken:  PARSERS_REF (kotatsu-parsers-redo revresi), MIHON_REF (varsayılan v0.20.1)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
MIHON_REPO="${MIHON_REPO:-https://github.com/mihonapp/mihon.git}"
MIHON_REF="${MIHON_REF:-v0.20.1}"
PARSERS_REF="${PARSERS_REF:-59c033ecfd}"
WORK="$ROOT/.work"
KEYSTORE="$ROOT/signing/pulsar.keystore"

# flavor adı -> "pkgSuffix|displayLang|nsfw"
flavor_args() {
    case "$1" in
        tr)       echo ".tr|tr|0" ;;
        tr18)     echo ".tr18|tr|1" ;;
        global)   echo ".global|all|0" ;;
        global18) echo ".global18|all|1" ;;
        test)     echo ".test|all|0" ;;
        test18)   echo ".test18|all|1" ;;
        *)        echo ".${1}|${1}|0" ;;
    esac
}
flavor_name() {
    case "$1" in
        tr) echo "Pulsar TR" ;;
        tr18) echo "Pulsar TR 18+" ;;
        global) echo "Pulsar Global" ;;
        global18) echo "Pulsar Global 18+" ;;
        test) echo "Pulsar Test" ;;
        test18) echo "Pulsar Test 18+" ;;
        *) echo "Pulsar $(echo "$1" | tr a-z A-Z)" ;;
    esac
}

FLAVORS="${FLAVORS:-tr,tr18,global,global18,test,test18}"

# Sürüm: versionCode ARTMALI ki bakım tamirleri cihazda "güncelleme" olsun.
# CI'da GITHUB_RUN_NUMBER (monotonik); yerelde sabit 1. versionName kontratı:
# major.minor TEMEL'e sabit (extensionLib), patch = run numarası → "1.6.<run>".
PULSAR_LIB_BASE="${PULSAR_LIB_BASE:-1.6}"
PULSAR_VERSION_CODE="${PULSAR_VERSION_CODE:-${GITHUB_RUN_NUMBER:-1}}"
PULSAR_VERSION_NAME="${PULSAR_VERSION_NAME:-${PULSAR_LIB_BASE}.${PULSAR_VERSION_CODE}}"
echo "▶ sürüm: versionCode=$PULSAR_VERSION_CODE versionName=$PULSAR_VERSION_NAME"

echo "▶ pulsar-v2 build  (mihon@$MIHON_REF, parsers@$PARSERS_REF, flavors: $FLAVORS)"
rm -rf "$WORK"
mkdir -p "$WORK" "$ROOT/repo-build/apk" "$ROOT/repo-build/icon"

# 0) Varlıklar bizim pipeline'ımızdan (Nyora: SourcePatches.kt vendor eder; biz
#    liveness/katalog verimizden JSON asset üretiyoruz).
python3 "$ROOT/scripts/06_prepare_assets.py"

# 0b) Klon birleştirme — aynı host+dil+NSFW'yi paylaşan katalog kaydı motor
#     kaynağına devredilir; taşınmış alan adları mirrors'a yazılır. Araç yoksa
#     build DURMAZ, uyarı verir (klonlar listede iki kez görünür).
PULSAR_BIN="${PULSAR_BIN:-$ROOT/../tools/pulsar/target/release/pulsar}"
if [ -x "$PULSAR_BIN" ]; then
    ( cd "$ROOT/.." && "$PULSAR_BIN" merge )
    # Veriyi Kotlin kaynağına göm: eklenti asset/Context erişimine muhtaç kalmasın.
    ( cd "$ROOT/.." && "$PULSAR_BIN" embed )
else
    echo "⚠ pulsar aracı yok ($PULSAR_BIN) — klon birleştirme ve gömme atlandı"
fi

# 1) Geçici resmi Mihon checkout'u — yalnız build API'si.
echo "── fetch upstream Mihon (build-time API only)"
git clone --quiet --depth 1 --branch "$MIHON_REF" "$MIHON_REPO" "$WORK/mihon"

# image-decoder gibi JitPack bağımlılıkları compileSdk 37 İSTER; CI adımı
# platforms;android-37.0 paketini kurar ( klasör adı android-37 ). NDK yalnız
# :app'in native build'indedir; eklenti modülü için runner'da kurulu son
# sürtere çek. Bu yalnız DERLEME konfigürasyonudur — kaynak koduna/AKT
# (source-api) dokunmaz, eklenti runtime davranışını değiştirmez.
sed -i -E 's/^android-sdk-compile = .*/android-sdk-compile = "37"/; s/^android-sdk-target = .*/android-sdk-target = "36"/' \
    "$WORK/mihon/gradle/mihon.versions.toml"
NDK_LATEST="$(ls "$ANDROID_HOME/ndk" 2>/dev/null | sort -V | tail -1 || true)"
if [ -n "$NDK_LATEST" ]; then
    sed -i -E "s/^android-ndk = .*/android-ndk = \"$NDK_LATEST\"/" "$WORK/mihon/gradle/mihon.versions.toml"
fi
echo "── SDK catalog patched: $(grep -E 'android-(sdk-compile|sdk-target|ndk)' "$WORK/mihon/gradle/mihon.versions.toml" | tr '\n' ' ')"

# 2) Modülümüzü bağla.
echo "── wire :pulsar-extension into the checkout"
cp -R "$ROOT/extension" "$WORK/mihon/pulsar-extension"
printf '\ninclude(":pulsar-extension")\n' >> "$WORK/mihon/settings.gradle.kts"

# 3) Her flavor'ı derle.
IFS=',' read -ra FLIST <<< "$FLAVORS"
for f in "${FLIST[@]}"; do
    IFS='|' read -r suffix lang nsfw <<< "$(flavor_args "$f")"
    name="$(flavor_name "$f")"
    echo "── assemble $name (lang=$lang nsfw=$nsfw)"
    (
        cd "$WORK/mihon"
        ./gradlew --quiet :pulsar-extension:assembleRelease \
            -PpulsarPkgSuffix="$suffix" \
            -PpulsarName="$name" \
            -PpulsarLang="$lang" \
            -PpulsarNsfw="$nsfw" \
            -PpulsarVersionCode="$PULSAR_VERSION_CODE" \
            -PpulsarVersionName="$PULSAR_VERSION_NAME" \
            -PparsersRef="$PARSERS_REF" \
            -PpulsarKeystore="$KEYSTORE"
    )
    out="$(find "$WORK/mihon/pulsar-extension/build/outputs/apk/release" -name '*.apk' | head -1)"
    [ -n "$out" ] || { echo "::error::$f flavor APK üretmedi"; exit 1; }
    cp "$out" "$ROOT/repo-build/apk/eu.kanade.tachiyomi.extension.all.pulsar${suffix}.apk"
done

# 4) id->kaynak haritası: bakım bacası (07_maintain.py) MIHON_<id>'leri ancak
#    bununla isimlendirebilir. Parsers deposu annotation taraması + katalog hash'i.
# Kısa sha fetch edilmez; GitHub API ile tam sha'ya çözülür.
FULL_REF="$(curl -sf "https://api.github.com/repos/Kotatsu-Redo/kotatsu-parsers-redo/commits/$PARSERS_REF" \
    | sed -n 's/.*"sha": "\([0-9a-f]\{40\}\)".*/\1/p' | head -1 || true)"
FULL_REF="${FULL_REF:-$PARSERS_REF}"
# `--depth 1` klonun İÇİNE ikinci sığ fetch atılamıyor (shallow repo başka
# bir shallow uç kabul etmiyor) — sabitlenmiş eski ref bu yüzden hep düşüyordu.
# Boş depoya doğrudan sha fetch'i ise çalışıyor (ölçüldü: 1389 .kt dosyası).
if git init --quiet "$WORK/parsers" &&
   git -C "$WORK/parsers" remote add origin \
        https://github.com/Kotatsu-Redo/kotatsu-parsers-redo &&
   git -C "$WORK/parsers" fetch --quiet --depth 1 origin "$FULL_REF" &&
   git -C "$WORK/parsers" checkout --quiet FETCH_HEAD; then
    python3 "$SCRIPTS/emit_source_map.py" "$WORK/parsers" \
        "$ROOT/extension/src/main/assets/catalogue.json" "$ROOT/repo-build/source_map.json"
else
    # APK'lar sabitlenmiş ref'ten derlendi; varsayılan dalın haritasını
    # yayınlamak paket üyeliğini sessizce değiştirir (test'e düşen/eklenen
    # kaynaklar). Depodaki harita o ref'e aittir, o korunur.
    echo "::warning::parsers revizyonu $FULL_REF alınamadı; depodaki source_map.json korunuyor"
    cp "$ROOT/repo/source_map.json" "$ROOT/repo-build/source_map.json"
fi

# 5) İndeksi APK'lardan üret (Nyora generate-repo örüntüsü: sürüm/parmak izi
#    APK'nın KENDİSİNDEN okunur, elle yazılamaz; kontrat bekçisi dahil).
python3 "$ROOT/scripts/generate_repo.py" "$ROOT/repo-build"

echo "✔ done → $ROOT/repo-build  (apk/, icon/, index.min.json, repo.json, source_map.json)"
