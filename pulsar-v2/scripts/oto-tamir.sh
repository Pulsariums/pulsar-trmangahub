#!/usr/bin/env bash
# Tamir kuyrugundan N kaynak alir, siteyi olcer, bilinen motor kaliplarindan (Madara,
# MangaReader/Themesia) 4 adimli curl dogrulamasini (liste > seri > bolum > gorsel) gecen
# ayari kataloga yazar. Gecenler "r" (teste doner); her deneme tamir-denemeleri.jsonl'a yazilir.
set -uo pipefail
N=${N:-30}; DIL=${DIL:-}
DP=pulsar-v2/depo; CAT=pulsar-v2/data/catalogue.json; LOG=$DP/tamir-denemeleri.jsonl
UA='Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36'
touch "$LOG"; : > /tmp/r.ids
get() { curl -sS -L -m 20 -A "$UA" -o "$2" -w '%{http_code} %{url_effective}' "$1" 2>/dev/null || echo "000 $1"; }
post() { curl -sS -L -m 20 -A "$UA" -X POST -o "$2" -w '%{http_code}' "$1" 2>/dev/null || echo 000; }
first_href() { grep -oE "href=\"[^\"]*$2[^\"]*\"" "$1" | sed -E 's/^href="//;s/"$//' | grep -vE 'feed|genre|/page/|#' | head -1; }
absu() { case "$1" in http*) echo "$1";; /*) echo "$2$1";; *) echo "$2/$1";; esac; }

jq -c --arg d "$DIL" --argjson n "$N" \
  '[.kayitlar[] | select(.etiket != "cloudflare") | select($d == "" or .dil == $d)] | .[0:$n][]' \
  "$DP/tamir-kuyrugu.json" > /tmp/q.jsonl
echo "kuyruktan alinan: $(wc -l < /tmp/q.jsonl)"

while read -r row; do
  id=$(jq -r .id <<<"$row"); dom=$(jq -r .alan_adi <<<"$row"); tur=$(jq -r .tur <<<"$row")
  ad=$(jq -r .ad <<<"$row"); dil=$(jq -r .dil <<<"$row"); nsfw=$(jq -r .nsfw <<<"$row")
  base=$(jq -r --arg d "$dom" '[.sources[]|select(.domain==$d)|.baseUrl][0] // empty' "$CAT"); [ -z "$base" ] && base="https://${dom#www.}"
  r=$(get "$base/" /tmp/h.html); code=${r%% *}; final=${r#* }
  host=$(sed -E 's|^(https?://[^/]+).*|\1|' <<<"$final"); [ "$code" = 000 ] && host="$base"
  cf=$(grep -ci 'just a moment\|challenge-platform\|cf-mitigated' /tmp/h.html 2>/dev/null || echo 0)
  ma=$(grep -ci 'wp-manga\|themes/madara' /tmp/h.html 2>/dev/null || echo 0)
  mr=$(grep -ci 'themes/mangareader\|themesia\|class="bsx"\|eplister\|ts-main' /tmp/h.html 2>/dev/null || echo 0)
  karar=""; motor=""; n=0; c=0; p=0; img=""; cfg='{}'; ajax=0
  if [ "$code" = 000 ]; then karar="erisilemiyor"
  elif [ "$cf" -gt 0 ]; then karar="cloudflare"
  elif [ "$ma" -gt 0 ]; then
    motor=madara
    get "$host/manga/?m_orderby=latest" /tmp/l.html >/dev/null; n=$(grep -o 'page-item-detail' /tmp/l.html | wc -l)
    s=$(first_href /tmp/l.html '/manga/[^/"]+/'); s=$(absu "$s" "$host")
    if [ -n "$s" ] && [ "$n" -gt 0 ]; then
      post "${s%/}/ajax/chapters/" /tmp/c.html >/dev/null; c=$(grep -o 'wp-manga-chapter' /tmp/c.html | wc -l); ajax=1
      if [ "$c" -eq 0 ]; then get "$s" /tmp/c.html >/dev/null; c=$(grep -o 'wp-manga-chapter' /tmp/c.html | wc -l); ajax=0; fi
      b=$(grep -oE 'href="[^"]+"' /tmp/c.html | sed -E 's/^href="//;s/"$//' | grep -vE '#|/feed' | grep -F "${s%/}/" | grep -vxF "$s" | head -1)
      [ -n "$b" ] && { get "$(absu "$b" "$host")" /tmp/b.html >/dev/null; p=$(grep -o 'wp-manga-chapter-img' /tmp/b.html | wc -l)
        img=$(grep -oE '<img[^>]*wp-manga-chapter-img[^>]*>' /tmp/b.html | grep -oE '(data-src|data-lazy-src|src)="\s*https?://[^"]+' | head -1 | sed -E 's/^[a-z-]+="\s*//'); }
    fi
    ax=$([ "$ajax" = 1 ] && echo '{url}ajax/chapters/' || echo '')
    cfg=$(jq -nc --arg h "$host" --arg ax "$ax" '{engine:"madara",listPath:"/manga/?m_orderby=latest",itemSelector:".page-item-detail",
      chapterSelector:"li.wp-manga-chapter a",readerSelector:".reading-content img",chapterAjaxUrl:$ax,
      searchUrl:($h+"/?s={query}&post_type=wp-manga")} | if .chapterAjaxUrl=="" then del(.chapterAjaxUrl) else . end')
  elif [ "$mr" -gt 0 ]; then
    motor=mangareader
    get "$host/manga/?order=update" /tmp/l.html >/dev/null; n=$(grep -o 'class="bsx"' /tmp/l.html | wc -l)
    s=$(grep -A3 'class="bsx"' /tmp/l.html | grep -oE 'href="[^"]+"' | head -1 | sed -E 's/^href="//;s/"$//'); s=$(absu "$s" "$host")
    if [ -n "$s" ] && [ "$n" -gt 0 ]; then
      get "$s" /tmp/c.html >/dev/null; c=$(grep -c 'data-num=' /tmp/c.html)
      b=$(grep -A4 'data-num=' /tmp/c.html | grep -oE 'href="[^"]+"' | head -1 | sed -E 's/^href="//;s/"$//')
      [ -n "$b" ] && { get "$(absu "$b" "$host")" /tmp/b.html >/dev/null
        p=$(grep -oE '"images":\[[^]]*\]' /tmp/b.html | grep -o 'http' | wc -l)
        [ "$p" -eq 0 ] && p=$(sed -n '/id="readerarea"/,/<\/div>/p' /tmp/b.html | grep -o '<img' | wc -l)
        img=$(grep -oE '"images":\["[^"]+' /tmp/b.html | head -1 | sed -E 's/.*\["//;s/\\//g'); }
    fi
    cfg=$(jq -nc --arg h "$host" '{engine:"mangareader",listPath:"/manga/?order=update",itemSelector:"div.bsx",
      chapterSelector:"#chapterlist li a, div.eph-num a",readerSelector:"div#readerarea img",
      searchUrl:($h+"/?s={query}")}')
  else karar="motor-taninmadi"
  fi
  ic=000; [ -n "$img" ] && ic=$(curl -sS -m 20 -A "$UA" -e "$host/" -o /dev/null -w '%{http_code}' "$img" 2>/dev/null || echo 000)
  if [ -z "$karar" ]; then
    if [ "$n" -gt 0 ] && [ "$c" -gt 0 ] && [ "$p" -gt 0 ] && [ "$ic" = 200 ]; then karar="duzeltildi"; else karar="dogrulama-gecmedi"; fi
  fi
  if [ "$karar" = duzeltildi ]; then
    if jq -e --arg d "$dom" 'any(.sources[]; .domain==$d)' "$CAT" >/dev/null; then
      jq --arg d "$dom" --arg h "$host" --argjson c "$cfg" '.sources |= map(if .domain==$d then
          .baseUrl=$h | .engine=$c.engine | .config=((.config // {}) + $c) | .selector_verified=true
          | .dead=false | del(.deadReason) | .origins=((.origins // []) + ["pulsar-oto-tamir"] | unique) else . end)' "$CAT" > /tmp/cat && cp /tmp/cat "$CAT"
      [ "$tur" = catalogue ] && echo "$id" >> /tmp/r.ids
    else
      jq --arg d "$dom" --arg h "$host" --arg ad "$ad" --arg dil "$dil" --argjson ns "${nsfw:-0}" --argjson c "$cfg" \
        '.sources += [{id:$d,name:$ad,lang:$dil,nsfw:$ns,domain:$d,baseUrl:$h,engine:$c.engine,config:$c,
          origins:["pulsar-oto-tamir"],selector_verified:true}] | .total_count=(.sources|length)' "$CAT" > /tmp/cat && cp /tmp/cat "$CAT"
      karar="yeni-katalog-kaydi"
    fi
  fi
  jq -nc --arg id "$id" --arg ad "$ad" --arg d "$dom" --arg host "$host" --arg code "$code" --arg motor "$motor" \
     --arg karar "$karar" --argjson n "$n" --argjson c "$c" --argjson p "$p" --arg ic "$ic" \
     '{id:$id,ad:$ad,alan_adi:$d,zaman:(now|todate),http:$code,adres:$host,motor:$motor,liste:$n,bolum:$c,sayfa:$p,gorsel_http:$ic,karar:$karar}' | tee -a "$LOG"
done < /tmp/q.jsonl
echo "teste donen (r): $(wc -l < /tmp/r.ids)"
