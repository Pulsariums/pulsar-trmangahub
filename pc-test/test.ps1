# Türkçe kaynakları KENDİ bilgisayarının IP'siyle dener (kurulum yok: PowerShell + curl.exe, Windows 10/11'de hazır gelir).
# Sorduğu soru: bu sitenin liste sayfası, JAR'ın göreceği gibi, senin ağından gerçekten manga listesi veriyor mu?
#   - Veri merkezi (GitHub Actions) IP'si engellenmiş ama sende açılan siteler "Cloudflare/engel" diye ayrışır.
#   - Sende de listesi çıkmayanlar gerçekten bozuk (site yapısı değişti / ölü / satılık).
# Kullanım:  calistir.cmd            -> hepsi
#            calistir.cmd -Sadece golge,nyx   -> adında/alan adında bu geçenler
#            calistir.cmd -Kapsam yayinda     -> yalnız yayındaki kayıtlar
param(
    [string]$Sadece = '',
    [ValidateSet('hepsi','yayinda')][string]$Kapsam = 'hepsi',
    [int]$Es = 8
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$UA = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36'
$url = 'https://raw.githubusercontent.com/Pulsariums/pulsar-trmangahub/main/sources/tr/sources.json'
Write-Host "Kaynak listesi indiriliyor..."
$raw = Invoke-RestMethod -Uri $url
$list = if ($raw -is [array]) { $raw } else { $raw.sources }
if ($Kapsam -eq 'yayinda') { $list = $list | Where-Object { $_.status -in 'published','cf_protected_published' } }
if ($Sadece) {
    $keys = $Sadece.ToLower().Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    $list = $list | Where-Object { $t = ("$($_.name) $($_.domain)").ToLower(); ($keys | Where-Object { $t.Contains($_) }).Count -gt 0 }
}
Write-Host ("Denenecek kayıt: {0} (aynı anda {1})" -f @($list).Count, $Es)

$work = {
    param($e, $UA)
    $cfMarks = 'just a moment','cf-browser-verification','challenge-platform','__cf_chl','cf-chl-','attention required! | cloudflare'
    $parkMarks = 'this domain is for sale','domain is for sale','buy this domain','domain parking','sedoparking','hugedomains.com','alan adı satılık','bu alan adı satılık','domain satılık'
    $eng = "$($e.engine)".ToLower()
    switch ($eng) {
        'madara'        { $paths = '/manga/','/';  $marks = 'page-item-detail','c-tabs-item','manga-item' }
        'mangareader'   { $paths = '/manga/?page=1'; $marks = 'bsx','listupd','utao' }
        'mangathemesia' { $paths = '/manga/?page=1'; $marks = 'bsx','listupd','utao' }
        default         { $paths = '/'; $marks = $null }
    }
    $base = "https://$($e.domain)"
    $res = [ordered]@{ ad = ($(if ($e.name) { $e.name } else { $e.domain })); domain = $e.domain; motor = $eng; kayit = $e.status; sonuc = ''; ayrinti = '' }
    $last = $null
    foreach ($p in $paths) {
        $tmp = [IO.Path]::GetTempFileName()
        try {
            $meta = & curl.exe -s -L -m 25 --max-redirs 5 -A $UA -H 'Accept-Language: tr-TR,tr;q=0.9,en;q=0.7' -o $tmp -w '%{http_code}|%{url_effective}' "$base$p" 2>$null
            $rc = $LASTEXITCODE
            $body = if (Test-Path $tmp) { [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8).ToLower() } else { '' }
        } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
        if ($rc -ne 0) {
            $kind = switch ($rc) { 6 {'dns'} 7 {'baglanti'} 28 {'zaman_asimi'} 35 {'ssl'} 60 {'ssl'} 51 {'ssl'} default {"curl_$rc"} }
            $last = @{ sonuc = $kind; ayrinti = "curl hata kodu $rc" }; continue
        }
        $code,$final = $meta.Split('|',2)
        $fh = ([uri]$final).Host -replace '^www\.',''
        $dh = $e.domain -replace '^www\.',''
        $cf = @($cfMarks | Where-Object { $body.Contains($_) }).Count -gt 0
        if ($cf) { $last = @{ sonuc = 'cloudflare'; ayrinti = "HTTP $code, doğrulama sayfası (tarayıcıda çerez gerekir)" }; continue }
        if ($fh -ne $dh) { $last = @{ sonuc = 'baska_siteye_yonlendi'; ayrinti = $fh }; continue }
        if (@($parkMarks | Where-Object { $body.Contains($_) }).Count -gt 0) { $last = @{ sonuc = 'satilik_park'; ayrinti = 'alan adı satılık/park sayfası' }; continue }
        if ([int]$code -ge 400) { $last = @{ sonuc = 'http_hata'; ayrinti = "HTTP $code" }; continue }
        if ($marks -eq $null) {
            $last = @{ sonuc = 'acildi'; ayrinti = "HTTP $code (motor bilinmiyor, liste doğrulanamadı)" }; break
        }
        $hit = @($marks | Where-Object { $body.Contains($_) }).Count -gt 0
        if ($hit) { $last = @{ sonuc = 'tamam'; ayrinti = "HTTP $code, $eng liste işareti bulundu ($p)" }; break }
        $last = @{ sonuc = 'yapi_degisti'; ayrinti = "HTTP $code ama $eng liste işareti yok ($p): site açılıyor, parser eski yapıya göre" }
    }
    $res.sonuc = $last.sonuc; $res.ayrinti = $last.ayrinti
    [pscustomobject]$res
}

$pool = [runspacefactory]::CreateRunspacePool(1, $Es); $pool.Open()
$jobs = foreach ($e in $list) {
    $ps = [powershell]::Create(); $ps.RunspacePool = $pool
    [void]$ps.AddScript($work).AddArgument($e).AddArgument($UA)
    [pscustomobject]@{ ps = $ps; h = $ps.BeginInvoke() }
}
$done = 0; $out = @()
foreach ($j in $jobs) {
    $out += $j.ps.EndInvoke($j.h); $j.ps.Dispose(); $done++
    Write-Progress -Activity 'Test' -Status "$done / $(@($jobs).Count)" -PercentComplete (100 * $done / @($jobs).Count)
}
$pool.Close()

$out | Sort-Object sonuc, ad | Format-Table ad, domain, motor, sonuc, ayrinti -AutoSize -Wrap | Out-String -Width 220 | Write-Host
Write-Host '--- Özet ---'
$out | Group-Object sonuc | Sort-Object Count -Descending | ForEach-Object { Write-Host ("{0,-24} {1}" -f $_.Name, $_.Count) }
$file = Join-Path $PSScriptRoot ("pc-sonuc-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
$out | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $file
Write-Host "Sonuç dosyası: $file"
