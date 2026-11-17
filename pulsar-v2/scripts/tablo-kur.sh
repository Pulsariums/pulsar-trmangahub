#!/usr/bin/env bash
# Havuz (dis kaynaklar), depo (bizim tek kaynak tablomuz) ve tamir kuyrugu uretici. Yalnizca jq.
set -euo pipefail
D=pulsar-v2/data
DP=pulsar-v2/depo
mkdir -p pulsar-v2/havuz "$DP"
LOG="$DP/tamir-denemeleri.jsonl"; touch "$LOG"

# repo-kapsami.csv -> { alan_adi: [repolar] }
jq -Rn '
  [inputs | split(",") | . as $f
   | ([range(0;$f|length)] | map(select($f[.] | startswith("eu.kanade.tachiyomi"))) | .[0]) as $i
   | select($i != null)
   | {d: ($f[$i+1]|ascii_downcase|sub("^www\\.";"")), r: ($f[1]|split(";"))}]
  | group_by(.d) | map({key:.[0].d, value:(map(.r)|add|unique)}) | from_entries
' "$D/repo-kapsami.csv" > /tmp/repolar.json

# eklentinin hic olusturmadigi kaynaklar (patches.json deadHosts/deadSources)
jq -n --slurpfile pt pulsar-v2/extension/src/main/assets/patches.json --slurpfile sm pulsar-v2/repo/source_map.json '
  ($pt[0].deadSources // []) as $DS
  | {hosts: (($pt[0].deadHosts // []) | map(ascii_downcase|sub("^www\\.";""))),
     ids: [ $sm[0].engine[]? | select(.name as $n | $DS | index($n)) | .id | tostring ]}
' > /tmp/kapali.json

# deneme sayilari (tamir-denemeleri.jsonl)
jq -s 'group_by(.id) | map({key:.[0].id, value:{sayi:length, son:(.[-1])}}) | from_entries' "$LOG" > /tmp/deneme.json

# HAVUZ
jq --slurpfile rp /tmp/repolar.json '
  ($rp[0]) as $R
  | {surum:1, uretildi:(now|todate), kaynak:"deduplicated.json + repo-kapsami.csv", toplam:length,
     kayitlar: map({id, marka:.brand, ad:.name, dil:.lang, nsfw, alan_adi:.domain,
                    diger_alan_adlari:(.altDomains//[]), motor:.engine, kokenler:.origins,
                    repolar:($R[(.domain|ascii_downcase|sub("^www\\.";""))]//[]),
                    kullanici_dogruladi:(.verified_by_user//false)})}
' "$D/deduplicated.json" > pulsar-v2/havuz/havuz.json

# DEPO
jq --slurpfile cat "$D/catalogue.json" --slurpfile hv pulsar-v2/havuz/havuz.json --slurpfile dn "$D/deneyim.json" \
   --slurpfile kp /tmp/kapali.json --slurpfile dz /tmp/deneme.json '
  def nd: (. // "") | ascii_downcase | sub("^www\\.";"");
  ($cat[0].sources | map({key:(.domain|nd), value:.}) | from_entries) as $C
  | ($hv[0].kayitlar | map({key:(.alan_adi|nd), value:.}) | from_entries) as $H
  | ($dn[0].kayitlar // []) as $DN
  | ($kp[0]) as $KP | ($dz[0]) as $DZ
  | .sources | to_entries | map(
      .key as $k | .value as $s | ($s.domain|nd) as $d | $C[$d] as $c | $H[$d] as $h
      | ([$DN[] | select((.kaynaklar // []) | map(nd) | index($d) != null)]) as $t
      | (($s.packages // [])[0] // "yok") as $g0
      | (($s.kind == "catalogue" and ($KP.hosts | index($d) != null)) or ($s.kind == "engine" and ($KP.ids | index($k) != null))) as $kapali
      | (if $kapali then "yok" else $g0 end) as $g
      | (($s.device.detail // "") | test("unknownhost|unable to resolve|could not resolve|nxdomain|no address associated"; "i")) as $dns
      | (if $s.dead == true then "imkansiz"
         elif $s.device.status == "pass" then "gecti"
         elif $s.device.status == "r" then "yeniden-test"
         elif $s.device.status == "cloudflare" or ($s.sorun // "") == "cloudflare" then "cloudflare"
         elif $dns then "alan-adi-aranacak"
         elif ($s.device.status // "") != "" then "tamir-edilebilir"
         elif $kapali then "tamir-edilebilir"
         elif $s.state == "active" then "gecti"
         else "test-edilmedi" end) as $e
      | { id: .key, tur: $s.kind, ad: $s.title, dil: $s.lang, nsfw: $s.nsfw,
          alan_adi: $s.domain, durum: $s.state, grup: $g, yayinda: ($g != "yok"),
          eklentide_kapali: $kapali,
          evre: (if $e == "imkansiz" then "imkansiz"
                 elif ($g == "tr" or $g == "tr18" or $g == "global" or $g == "global18") then "ana-grupta"
                 elif $g == "test" then "testte"
                 else "tamir-kuyrugunda" end),
          motor: ($c.engine // $h.motor // null),
          kokenler: ($c.origins // $h.kokenler // []),
          repolar: ($h.repolar // []),
          katalogda: ($c != null), havuzda: ($h != null),
          secici_dogrulandi: ($c.selector_verified // false),
          cihaz: ($s.device.status // null),
          hata_adimi: ($s.device_step // null),
          hata_mesaji: ($s.device.detail // null),
          saglik: ($s.health.status // null),
          olu: ($s.dead // false), ulasilamaz: ($s.unreachable // false),
          sorun: ($s.sorun // null), not: ($s.note // null),
          tamir_kayitlari: ($t | map(.id)),
          tamir_denemesi: ($DZ[.key].sayi // 0),
          son_tamir: ($DZ[.key].son.karar // null),
          tamir_edildi: ((($t | map(select((.basari // 0) > 0)) | length) > 0) or $e == "yeniden-test"),
          etiket: $e })
  | {surum:1, uretildi:(now|todate), toplam:length, kayitlar:.}
' "$D/source-status.json" > "$DP/kaynaklar.json"

# TAMIR KUYRUGU: yayinda olmayan, imkansiz olmayan her kaynak. Oncelik: TR, katalog (secici ile
# tamir edilebilir), az denenmis, liste > sayfa > detay > bolum > kapak > arama.
jq '
  def ao: {"list":0,"pages":1,"details":2,"chapters":3,"covers":4,"search":5}[. // ""] // 6;
  [.kayitlar[] | select(.evre == "tamir-kuyrugunda")
   | {id, ad, alan_adi, dil, nsfw, tur, motor, etiket, hata_adimi, hata_mesaji, eklentide_kapali,
      tamir_denemesi, son_tamir, repolar}]
  | sort_by([(if .dil == "tr" then 0 else 1 end), (if .tur == "catalogue" then 0 else 1 end),
             .tamir_denemesi, (.hata_adimi | ao), .alan_adi])
  | {uretildi:(now|todate), toplam:length,
     ozet:{tr:(map(select(.dil=="tr"))|length), katalog:(map(select(.tur=="catalogue"))|length),
           etiket:(group_by(.etiket)|map({key:.[0].etiket, value:length})|from_entries)},
     kayitlar:.}
' "$DP/kaynaklar.json" > "$DP/tamir-kuyrugu.json"

echo '--- havuz'; jq '{toplam, repolu:([.kayitlar[]|select(.repolar|length>0)]|length)}' pulsar-v2/havuz/havuz.json
echo '--- depo evre'; jq -r '.kayitlar|group_by(.evre)|map("\(.[0].evre)\t\(length)")|.[]' "$DP/kaynaklar.json"
echo '--- depo grup'; jq -r '.kayitlar|group_by(.grup)|map("\(.[0].grup)\t\(length)")|.[]' "$DP/kaynaklar.json"
echo '--- kuyruk'; jq -c '{toplam, ozet}' "$DP/tamir-kuyrugu.json"
