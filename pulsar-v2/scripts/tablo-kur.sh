#!/usr/bin/env bash
# Havuz (dis kaynaklar) ve depo (bizim tek kaynak tablomuz) uretici. Yalnizca jq.
set -euo pipefail
D=pulsar-v2/data
mkdir -p pulsar-v2/havuz pulsar-v2/depo

# repo-kapsami.csv -> { alan_adi: [repolar] }
jq -Rn '
  [inputs | split(",") | . as $f
   | ([range(0;$f|length)] | map(select($f[.] | startswith("eu.kanade.tachiyomi"))) | .[0]) as $i
   | select($i != null)
   | {d: ($f[$i+1]|ascii_downcase|sub("^www\\.";"")), r: ($f[1]|split(";"))}]
  | group_by(.d) | map({key:.[0].d, value:(map(.r)|add|unique)}) | from_entries
' "$D/repo-kapsami.csv" > /tmp/repolar.json

# HAVUZ: dis repolardan gelen her sey (tekillestirilmis)
jq --slurpfile rp /tmp/repolar.json '
  ($rp[0]) as $R
  | {surum:1, uretildi:(now|todate), kaynak:"deduplicated.json + repo-kapsami.csv", toplam:length,
     kayitlar: map({id, marka:.brand, ad:.name, dil:.lang, nsfw, alan_adi:.domain,
                    diger_alan_adlari:(.altDomains//[]), motor:.engine, kokenler:.origins,
                    repolar:($R[(.domain|ascii_downcase|sub("^www\\.";""))]//[]),
                    kullanici_dogruladi:(.verified_by_user//false)})}
' "$D/deduplicated.json" > pulsar-v2/havuz/havuz.json

# DEPO: bizim tek tablo (id = source-status anahtari, metin olarak)
jq --slurpfile cat "$D/catalogue.json" --slurpfile hv pulsar-v2/havuz/havuz.json --slurpfile dn "$D/deneyim.json" '
  def nd: (. // "") | ascii_downcase | sub("^www\\.";"");
  ($cat[0].sources | map({key:(.domain|nd), value:.}) | from_entries) as $C
  | ($hv[0].kayitlar | map({key:(.alan_adi|nd), value:.}) | from_entries) as $H
  | ($dn[0].kayitlar // []) as $DN
  | .sources | to_entries | map(
      .value as $s | ($s.domain|nd) as $d | $C[$d] as $c | $H[$d] as $h
      | ([$DN[] | select((.kaynaklar // []) | map(nd) | index($d) != null)]) as $t
      | (($s.packages // [])[0] // "yok") as $g
      | (if $s.dead == true then "imkansiz"
         elif $s.device.status == "pass" then "gecti"
         elif $s.device.status == "r" then "yeniden-test"
         elif $s.device.status == "cloudflare" then "cloudflare"
         elif $s.unreachable == true then "alan-adi-aranacak"
         elif ($s.device.status // "") != "" then "tamir-edilebilir"
         elif $s.state == "active" then "gecti"
         else "test-edilmedi" end) as $e
      | { id: .key, tur: $s.kind, ad: $s.title, dil: $s.lang, nsfw: $s.nsfw,
          alan_adi: $s.domain, durum: $s.state,
          grup: $g,
          yayinda: ($g != "yok"),
          evre: (if $e == "imkansiz" then "imkansiz"
                 elif ($g == "tr" or $g == "tr18" or $g == "global" or $g == "global18") then "ana-grupta"
                 elif $g == "test" then "testte"
                 else "yayin-disi" end),
          motor: ($c.engine // $h.motor // null),
          kokenler: ($c.origins // $h.kokenler // []),
          repolar: ($h.repolar // []),
          katalogda: ($c != null), havuzda: ($h != null),
          secici_dogrulandi: ($c.selector_verified // false),
          cihaz: ($s.device.status // null),
          hata_adimi: ($s.device_step // null),
          hata_mesaji: ($s.device.detail // null),
          saglik: ($s.health.status // null),
          olu: ($s.dead // false),
          ulasilamaz: ($s.unreachable // false),
          sorun: ($s.sorun // null),
          not: ($s.note // null),
          tamir_kayitlari: ($t | map(.id)),
          tamir_edildi: (($t | map(select((.basari // 0) > 0)) | length) > 0 or $e == "yeniden-test"),
          etiket: $e,
          denemeler: [] })
  | {surum:1, uretildi:(now|todate), toplam:length, kayitlar:.}
' "$D/source-status.json" > pulsar-v2/depo/kaynaklar.json

echo '--- havuz'; jq '{toplam, repolu:([.kayitlar[]|select(.repolar|length>0)]|length)}' pulsar-v2/havuz/havuz.json
echo '--- depo etiket'; jq -r '.kayitlar|group_by(.etiket)|map("\(.[0].etiket)\t\(length)")|.[]' pulsar-v2/depo/kaynaklar.json
echo '--- depo evre'; jq -r '.kayitlar|group_by(.evre)|map("\(.[0].evre)\t\(length)")|.[]' pulsar-v2/depo/kaynaklar.json
echo '--- depo grup'; jq -r '.kayitlar|group_by(.grup)|map("\(.[0].grup)\t\(length)")|.[]' pulsar-v2/depo/kaynaklar.json
echo '--- katalogda/havuzda/tamirli'; jq '{toplam, katalogda:([.kayitlar[]|select(.katalogda)]|length), havuzda:([.kayitlar[]|select(.havuzda)]|length), tamirli:([.kayitlar[]|select(.tamir_edildi)]|length)}' pulsar-v2/depo/kaynaklar.json
