#!/usr/bin/env bash
#
# Pulsar-V2 — Nyora porter örüntüsüyle kendi eklentimizi KENDİ verimizle derler.
# Kopya değil, örnek: geçici (throwaway) resmi Mihon checkout'u yalnız eklenti
# DERLEME API'si için kullanılır; uygulama asla derlenmez. Modülümüz oraya
# :pulsar-extension olarak bağlanır; imza anahtarı CI'da her derlemede üretilir
# ve parmak izi APK'dan OTOMATİK okunur (generate_repo.py).
#
# Kullanım:  pulsar_build.sh [flavor ...]
#            FLAVORS="tr,tr18,global,global18" pulsar_build.sh
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
        *)        echo ".${1}|${1}|0" ;;
    esac
}
flavor_name() {
    case "$1" in
        tr) echo "Pulsar TR" ;;
        tr18) echo "Pulsar TR 18+" ;;
        global) echo "Pulsar Global" ;;
        global18) echo "Pulsar Global 18+" ;;
        *) echo "Pulsar $(echo "$1" | tr a-z A-Z)" ;;
    esac
}

FLAVORS="${FLAVORS:-tr,tr18,global,global18}"

echo "▶ pulsar-v2 build  (mihon@$MIHON_REF, parsers@$PARSERS_REF, flavors: $FLAVORS)"
rm -rf "$WORK"
mkdir -p "$WORK" "$ROOT/repo-build/apk" "$ROOT/repo-build/icon"

# 0) Varlıklar bizim pipeline'ımızdan (Nyora: SourcePatches.kt vendor eder; biz
#    liveness/katalog verimizden JSON asset üretiyoruz).
python3 "$ROOT/scripts/06_prepare_assets.py"

# 1) Geçici resmi Mihon checkout'u — yalnız build API'si.
echo "── fetch upstream Mihon (build-time API only)"
git clone --quiet --depth 1 --branch "$MIHON_REF" "$MIHON_REPO" "$WORK/mihon"

# android-37 henüz önizleme kanalında ve runner'larda kurulabilir değil;
# geçici checkout'un KATALOĞUNU kararlı API 36'ya sabitle. NDK yalnız :app'in
# native build'indedir; eklenti modülü için runner'da kurulu son sürtere çek.
# Bu yalnız DERLEME konfigürasyonudur — kaynak koduna/AKT (source-api) dokunmaz,
# eklenti runtime davranışını (tachiyomix.extensionLib) değiştirmez.
sed -i -E 's/^android-sdk-compile = .*/android-sdk-compile = "36"/; s/^android-sdk-target = .*/android-sdk-target = "36"/' \
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
            -PparsersRef="$PARSERS_REF" \
            -PpulsarKeystore="$KEYSTORE"
    )
    out="$(find "$WORK/mihon/pulsar-extension/build/outputs/apk/release" -name '*.apk' | head -1)"
    [ -n "$out" ] || { echo "::error::$f flavor APK üretmedi"; exit 1; }
    cp "$out" "$ROOT/repo-build/apk/eu.kanade.tachiyomi.extension.all.pulsar${suffix}.apk"
done

# 4) İndeksi APK'lardan üret (Nyora generate-repo örüntüsü: sürüm/parmak izi
#    APK'nın KENDİSİNDEN okunur, elle yazılamaz; kontrat bekçisi dahil).
python3 "$ROOT/scripts/generate_repo.py" "$ROOT/repo-build"

echo "✔ done → $ROOT/repo-build  (apk/, icon/, index.min.json, repo.json)"
