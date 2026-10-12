#!/usr/bin/env bash
# Canlı test sonucunu data/live altına işler: <bucket>.json (son sonuç) ve history.json (kaynak başına seri).
# Kullanım: scripts/live_merge.sh <bucket> <sonuclar.json>
set -euo pipefail
bucket="$1"; res="$2"
dir=data/live; mkdir -p "$dir"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
hist="$dir/history.json"
[ -f "$hist" ] || echo '{}' > "$hist"

jq --arg now "$now" --slurpfile res "$res" '
  reduce $res[0][] as $r (.;
    .[$r.id] = (
      (.[$r.id] // {first_seen: $now, ok_streak: 0, fail_streak: 0})
      | .name = $r.name
      | .domain = ($r.domain // .domain)
      | .checked = $now
      | if $r.ok then
          .ok_streak += 1 | .fail_streak = 0 | .last_ok = $now | .error_class = null | .last_error = null | .stage = "image"
        else
          .fail_streak += 1 | .ok_streak = 0 | .last_fail = $now
          | .error_class = $r.error_class | .last_error = $r.error | .stage = $r.stage
        end
    ))' "$hist" > "$hist.tmp"
mv "$hist.tmp" "$hist"

jq --arg now "$now" '{checked_at: $now, results: .}' "$res" > "$dir/$bucket.json"
