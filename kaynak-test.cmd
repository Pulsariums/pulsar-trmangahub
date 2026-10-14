@echo off
chcp 65001 >nul
rem Tek dosya: repodan listeyi çeker, siteleri bu bilgisayarın IP'siyle dener, JAR üretimini repoda başlatır.
rem Kullanım: çift tıkla (menü), veya: kaynak-test.cmd yayinda  /  kaynak-test.cmd golge nyx
set "KT_ARGS=%*"
set "KT_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:KT_SELF,[Text.Encoding]::UTF8); $i=$s.IndexOf('#'+'PS-BASLA'); Invoke-Expression $s.Substring($i)"
echo.
pause
exit /b
#PS-BASLA
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Repo = 'Pulsariums/pulsar-trmangahub'
$UA = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36'
$Es = 8

# ---- Ne test edilecek? (argüman yoksa menü) ----
$argText = "$env:KT_ARGS".Trim()
$Kapsam = 'hepsi'; $Anahtar = @()
if ($argText -eq '') {
    Write-Host ''
    Write-Host '  1) Hepsi (171 kayıt)'
    Write-Host '  2) Yalnız yayındakiler'
    Write-Host '  3) Ada/alan adına göre seç (örn: golge nyx)'
    $c = Read-Host '  Seçim [1]'
    if ($c -eq '2') { $Kapsam = 'yayinda' }
    elseif ($c -eq '3') { $Anahtar = (Read-Host '  Anahtar kelimeler (boşlukla)').ToLower().Split(' ', [StringSplitOptions]::RemoveEmptyEntries) }
} else {
    $t = $argText.ToLower().Split(' ', [StringSplitOptions]::RemoveEmptyEntries)
    if ($t[0] -eq 'yayinda') { $Kapsam = 'yayinda' } elseif ($t[0] -ne 'hepsi') { $Anahtar = $t }
}

Write-Host 'Kaynak listesi repodan indiriliyor...'
$raw = Invoke-RestMethod -Uri "https://raw.githubusercontent.com/$Repo/main/sources/tr/sources.json"
$list = if ($raw -is [array]) { $raw } else { $raw.sources }
if ($Kapsam -eq 'yayinda') { $list = $list | Where-Object { $_.status -in 'published','cf_protected_published' } }
if ($Anahtar.Count) { $list = $list | Where-Object { $s = ("$($_.name) $($_.domain)").ToLower(); ($Anahtar | Where-Object { $s.Contains($_) }).Count -gt 0 } }
$list = @($list)
Write-Host ("Denenecek kayıt: {0} (aynı anda {1})" -f $list.Count, $Es)
if (-not $list.Count) { Write-Host 'Eşleşen kayıt yok.'; return }

# ---- Her site: liste sayfasını bu bilgisayarın IP'siyle çek, motorun liste işaretini ara ----
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
    $last = @{ sonuc = 'bilinmiyor'; ayrinti = '' }
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
        if (@($cfMarks | Where-Object { $body.Contains($_) }).Count -gt 0) { $last = @{ sonuc = 'cloudflare'; ayrinti = "HTTP $code, doğrulama sayfası (tarayıcıda çerez gerekir)" }; continue }
        if ($fh -ne $dh) { $last = @{ sonuc = 'baska_siteye_yonlendi'; ayrinti = $fh }; continue }
        if (@($parkMarks | Where-Object { $body.Contains($_) }).Count -gt 0) { $last = @{ sonuc = 'satilik_park'; ayrinti = 'alan adı satılık/park sayfası' }; continue }
        if ([int]$code -ge 400) { $last = @{ sonuc = 'http_hata'; ayrinti = "HTTP $code" }; continue }
        if ($marks -eq $null) { $last = @{ sonuc = 'acildi'; ayrinti = "HTTP $code (motor bilinmiyor, liste doğrulanamadı)" }; break }
        if (@($marks | Where-Object { $body.Contains($_) }).Count -gt 0) { $last = @{ sonuc = 'tamam'; ayrinti = "HTTP $code, $eng liste işareti var ($p)" }; break }
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
    Write-Progress -Activity 'Test' -Status "$done / $($list.Count)" -PercentComplete (100 * $done / $list.Count)
}
$pool.Close()

$out | Sort-Object sonuc, ad | Format-Table ad, domain, motor, sonuc, ayrinti -AutoSize -Wrap | Out-String -Width 220 | Write-Host
Write-Host '--- Özet ---'
$out | Group-Object sonuc | Sort-Object Count -Descending | ForEach-Object { Write-Host ("{0,-24} {1}" -f $_.Name, $_.Count) }
$dir = Split-Path -Parent $env:KT_SELF
$file = Join-Path $dir ("kaynak-test-sonuc-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
$out | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $file
Write-Host "Sonuç dosyası: $file"

# ---- Üretim: sitesi bu bilgisayarda açılan ama JAR'ı olmayan/eski yapıda olanlar repoda JAR olarak üretilsin ----
$ham = $list | Where-Object { -not $_.formats.jar.parser } | ForEach-Object { $_.domain }
$uret = @($out | Where-Object { $_.sonuc -in 'yapi_degisti','acildi','tamam' -and ($_.sonuc -ne 'tamam' -or $ham -contains $_.domain) } | ForEach-Object { $_.domain } | Sort-Object -Unique)
Write-Host ''
if (-not $uret.Count) { Write-Host 'Üretilecek site yok.'; return }
$linkler = $uret -join ' '
Write-Host ("JAR üretimine gönderilecek site: {0}" -f $uret.Count)
Write-Host $linkler
try { Set-Clipboard -Value $linkler } catch {}
if ($env:GH_TOKEN) {
    $a = Read-Host 'GH_TOKEN bulundu. Repo workflow''u şimdi başlatılsın mı? (e/h)'
    if ($a -eq 'e') {
        $body = @{ ref = 'main'; inputs = @{ url = $linkler; format = 'jar'; engine = 'derin'; register = 'true' } } | ConvertTo-Json -Depth 4
        Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$Repo/actions/workflows/kaynak-ekle.yml/dispatches" `
            -Headers @{ Authorization = "Bearer $env:GH_TOKEN"; Accept = 'application/vnd.github+json' } -Body $body -ContentType 'application/json'
        Write-Host "Workflow başlatıldı: https://github.com/$Repo/actions"
    }
} else {
    Write-Host 'Liste panoya kopyalandı. Açılan sayfada "Run workflow" > url kutusuna yapıştır (Ctrl+V) > çalıştır.'
    Start-Process "https://github.com/$Repo/actions/workflows/kaynak-ekle.yml"
}
