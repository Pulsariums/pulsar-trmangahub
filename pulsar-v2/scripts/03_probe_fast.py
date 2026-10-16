#!/usr/bin/env python3
"""Pulsar-V2 - Aşama 3: Otomatik Tamirat & Detaylı Canlılık Teşhis Motoru.

Bu script her bir kaynağı ve alternatif domainlerini derinlemesine inceler:
1. Hata Teşhisi:
   - OLU_DNS: Domain süresi dolmuş veya DNS kaydı silinmiş (kurtarılamaz)
   - OLU_HTTP: Sunucu 404/521/523 veriyor (site kapanmış)
   - YEREL_ENGEL: Türkiye ISP/ağ engeli (yerelde engelli ama CI veya VPN ile açık)
   - CLOUDFLARE: Anti-bot koruması (Mihon WebView ile aşılabilir)
   - CANLI: Doğrudan sorunsuz çalışanlar

2. Otomatik Tamirat Mekanizmaları:
   - Yönlendirme Tamiratı: Site başka bir domaine 301/302 yönleniyorsa, canonical domain otomatik güncellenir.
   - Alternatif Domain Tamiratı: Birincil domain ölü ama altDomains içinden biri canlıysa, kaynak otomatik tamir edilir.
   - Kullanıcı Zemin Gerçeği Koruması: Kullanıcının doğruladığı kaynaklar asla silinmez.

Çıktılar:
- pulsar-v2/data/liveness.json (Derinlemesine teşhis veritabanı)
- pulsar-v2/data/alive_sources.json (Canlı ve tamir edilmiş nihai kaynaklar)
- pulsar-v2/DIAGNOSTICS_REPORT.md (Kullanıcı için detaylı hata ve tamirat raporu)
"""

import argparse
import concurrent.futures
import json
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PULSAR_V2_DIR = os.path.join(ROOT_DIR, "pulsar-v2")
DATA_DIR = os.path.join(PULSAR_V2_DIR, "data")
IN_FILE = os.path.join(DATA_DIR, "deduplicated.json")
OUT_LIVENESS = os.path.join(DATA_DIR, "liveness.json")
OUT_ALIVE = os.path.join(DATA_DIR, "alive_sources.json")
REPORT_FILE = os.path.join(PULSAR_V2_DIR, "DIAGNOSTICS_REPORT.md")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def clean_domain(url_or_domain):
    if not url_or_domain:
        return ""
    d = str(url_or_domain).strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = d.split("/")[0]
    d = re.sub(r"^www\.", "", d)
    return d


def check_dns(domain):
    try:
        socket.getaddrinfo(domain, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True
    except socket.gaierror:
        return False
    except Exception:
        return False


def test_url(url, timeout=7):
    """URL'yi test eder. (status, http_code, final_url, reason) döner."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            final_url = resp.geturl()
            headers = dict(resp.headers)
            is_cf = "cloudflare" in headers.get("server", "").lower()
            return "alive", code, final_url, "Bağlantı başarılı" + (" (Cloudflare)" if is_cf else "")
    except urllib.error.HTTPError as e:
        code = e.code
        final_url = e.geturl()
        if code in (403, 503):
            return "cf_protected", code, final_url, f"HTTP {code} (Cloudflare / Anti-Bot)"
        if code in (404, 410, 521, 523):
            return "dead_http", code, final_url, f"HTTP {code} (Site kapalı / sayfa yok)"
        if code in (301, 302, 307, 308):
            return "alive", code, final_url, f"HTTP {code} Yönlendirme"
        return "warning_http", code, final_url, f"HTTP {code}"
    except Exception as e:
        err = str(e)
        return "unreachable", 0, url, f"Ağ/Bağlantı hatası: {err[:60]}"


SPAM_GAMBLING_PATTERN = re.compile(
    r"(bet|casino|slot|poker|judi|koplo|gacor|togel|789bet|situsbet|linkgacor|depo|zeus)",
    re.IGNORECASE
)


def is_spam_domain(domain):
    return bool(SPAM_GAMBLING_PATTERN.search(domain))


def probe_and_repair_source(src):
    domain = src["domain"]
    base_url = src.get("baseUrl") or f"https://{domain}"
    is_verified = src.get("verified_by_user", False)
    alt_domains = src.get("altDomains", [])

    # 1. Ana domain DNS kontrolü
    has_dns = check_dns(domain)
    if not has_dns:
        # Alternatif domain varsa hemen tamir dene!
        for alt in alt_domains:
            if check_dns(alt):
                alt_status, alt_code, alt_final, alt_reason = test_url(f"https://{alt}")
                if alt_status in ("alive", "cf_protected"):
                    # OTOMATİK TAMİR EDİLDİ!
                    src["domain"] = alt
                    src["baseUrl"] = f"https://{alt}"
                    return {
                        "domain": domain,
                        "repaired_domain": alt,
                        "status": "OTOMATIK_TAMIR_ALTERNATIF",
                        "alive": True,
                        "reason": f"Eski domain ({domain}) DNS ölüydü, çalışan alternatif domain ({alt}) ile otomatik onarıldı.",
                        "source": src
                    }

        return {
            "domain": domain,
            "status": "DOGRULANMIS_YEREL_DNS_HATA" if is_verified else "OLU_DNS_KAYDI_YOK",
            "alive": is_verified,
            "reason": f"DNS kaydı çözümlenemedi (NXDOMAIN / domain süresi bitmiş veya park edilmiş).",
            "source": src
        }

    # 2. Ana domain HTTP testi
    st, code, final_url, reason = test_url(base_url)

    # Otomatik yönlendirme tamiratı kontrolü
    final_domain = clean_domain(final_url)
    if st == "alive" and final_domain and final_domain != domain:
        # Kumar/spam alan adına yönlenmişse kesinlikle kabul etme, ölü say!
        if is_spam_domain(final_domain):
            return {
                "domain": domain,
                "status": "OLU_SPAM_KUMAR_YONLENDIRME",
                "alive": False,
                "reason": f"Domain süresi bitmiş, kumar/spam sitesine yönlendirilmiş ({final_domain}).",
                "source": src
            }

        # Site başka bir meşru yere yönlendiriyor, domain'i otomatik güncelle!
        src["domain"] = final_domain
        src["baseUrl"] = f"https://{final_domain}"
        src["altDomains"] = sorted(list(set(src["altDomains"] + [domain])))
        return {
            "domain": domain,
            "repaired_domain": final_domain,
            "status": "OTOMATIK_TAMIR_YONLENDIRME",
            "alive": True,
            "reason": f"Site {domain} adresinden {final_domain} adresine taşınmış, otomatik onarıldı.",
            "source": src
        }

    if st == "alive":
        return {
            "domain": domain,
            "status": "CANLI_DOGRU",
            "alive": True,
            "reason": f"HTTP {code} doğrudan açık.",
            "source": src
        }

    if st == "cf_protected":
        return {
            "domain": domain,
            "status": "CLOUDFLARE_KORUMALI",
            "alive": True,
            "reason": f"Cloudflare koruması aktif (Mihon dahili WebView çözücüsü ile aşılabilir).",
            "source": src
        }

    if st == "dead_http":
        # Alternatif domainlerde şansımızı deneyelim
        for alt in alt_domains:
            if check_dns(alt):
                alt_st, alt_code, alt_final, alt_rs = test_url(f"https://{alt}")
                if alt_st in ("alive", "cf_protected"):
                    src["domain"] = alt
                    src["baseUrl"] = f"https://{alt}"
                    return {
                        "domain": domain,
                        "repaired_domain": alt,
                        "status": "OTOMATIK_TAMIR_ALTERNATIF",
                        "alive": True,
                        "reason": f"Ana domain ({domain}) HTTP {code} veriyordu, alternatif ({alt}) ile otomatik onarıldı.",
                        "source": src
                    }
        return {
            "domain": domain,
            "status": "DOGRULANMIS_KORUNAN" if is_verified else "OLU_HTTP_SUNUCU_KAPALI",
            "alive": is_verified,
            "reason": f"Sunucu HTTP {code} dönüyor (Sayfa bulunamadı veya sunucu kapalı).",
            "source": src
        }

    # Ağ/ISP Engeli (unreachable)
    return {
        "domain": domain,
        "status": "DOGRULANMIS_YEREL_ENGEL" if is_verified else "YEREL_AG_ISP_ENGELI",
        "alive": is_verified,
        "reason": f"Yerel ağ/ISP bağlantı reddi (SSL/Reset). Farklı ağ veya CI üzerinde kontrol edilmeli.",
        "source": src
    }


def main():
    parser = argparse.ArgumentParser(description="Pulsar-V2 Otomatik Tamirat & Teshis Motoru")
    parser.add_argument("--lang", default="tr", help="Hedef dil")
    parser.add_argument("--workers", type=int, default=25, help="Eşzamanlı worker sayısı")
    args = parser.parse_args()

    if not os.path.exists(IN_FILE):
        print(f"[HATA] {IN_FILE} bulunamadi!")
        return

    with open(IN_FILE, encoding="utf-8") as f:
        sources = json.load(f)

    if args.lang != "all":
        target_sources = [s for s in sources if s.get("lang") == args.lang]
    else:
        target_sources = sources

    print(f"Teşhis ve Otomatik Tamirat Başlıyor: {len(target_sources)} kaynak inceleniyor...")
    start_time = time.time()

    results = []
    alive_sources = []
    dead_sources = []
    repaired_sources = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_src = {executor.submit(probe_and_repair_source, s): s for s in target_sources}
        for future in concurrent.futures.as_completed(future_to_src):
            res = future.result()
            results.append(res)
            if res["status"].startswith("OTOMATIK_TAMIR"):
                repaired_sources.append(res)
            if res["alive"]:
                alive_sources.append(res["source"])
            else:
                dead_sources.append(res)

    elapsed = time.time() - start_time

    # İstatistikler
    status_counts = {}
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    # Kayıtlar
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_LIVENESS, "w", encoding="utf-8") as f:
        json.dump({
            "tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tested": len(target_sources),
            "alive_count": len(alive_sources),
            "repaired_count": len(repaired_sources),
            "dead_count": len(dead_sources),
            "breakdown": status_counts,
            "results": results
        }, f, ensure_ascii=False, indent=2)

    with open(OUT_ALIVE, "w", encoding="utf-8") as f:
        json.dump(alive_sources, f, ensure_ascii=False, indent=2)

    # Detaylı Kullanıcı Raporu
    report_lines = [
        "# Pulsar-V2 Kaynak Teşhis ve Otomatik Tamirat Raporu",
        f"\n**Tarih:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        f"**Toplam İncelenen Kaynak:** {len(target_sources)}",
        f"**Canlı / Yayına Uygun:** {len(alive_sources)}",
        f"**Otomatik Onarılan:** {len(repaired_sources)}",
        f"**Ölü / Elenen:** {len(dead_sources)}\n",
        "## Teşhis Dağılımı\n",
        "| Durum Kodu | Adet | Anlamı ve Çözüm |",
        "|---|---|---|",
        f"| `CANLI_DOGRU` | {status_counts.get('CANLI_DOGRU', 0)} | Doğrudan açık ve sorunsuz çalışan kaynaklar. |",
        f"| `OTOMATIK_TAMIR_YONLENDIRME` | {status_counts.get('OTOMATIK_TAMIR_YONLENDIRME', 0)} | Site yeni domaine taşınmış, sistem otomatik tespit edip onardı. |",
        f"| `OTOMATIK_TAMIR_ALTERNATIF` | {status_counts.get('OTOMATIK_TAMIR_ALTERNATIF', 0)} | Ana domain ölmüş, ama yedek/alternatif domain canlı bulunup otomatik onarıldı. |",
        f"| `CLOUDFLARE_KORUMALI` | {status_counts.get('CLOUDFLARE_KORUMALI', 0)} | Cloudflare koruması aktif. Mihon içinde 'WebView ile Aç' ile sorunsuz açılır. |",
        f"| `YEREL_AG_ISP_ENGELI` | {status_counts.get('YEREL_AG_ISP_ENGELI', 0)} | Türkiye yerel servis sağlayıcı/ağ engeli. CI sunucusunda doğrulanmalı. |",
        f"| `OLU_DNS_KAYDI_YOK` | {status_counts.get('OLU_DNS_KAYDI_YOK', 0)} | Domain süresi dolmuş veya silinmiş (kurtarılamaz ölü). |",
        f"| `OLU_HTTP_SUNUCU_KAPALI` | {status_counts.get('OLU_HTTP_SUNUCU_KAPALI', 0)} | Sunucu HTTP 404/521/523 veriyor (site kapatılmış). |",
        f"| `DOGRULANMIS_KORUNAN` | {status_counts.get('DOGRULANMIS_KORUNAN', 0) + status_counts.get('DOGRULANMIS_YEREL_ENGEL', 0)} | Kullanıcı Kototoro'da doğruladığı için teste takılsa dahi korunanlar. |\n"
    ]

    if repaired_sources:
        report_lines.append("## Otomatik Onarılan Kaynaklar\n")
        report_lines.append("| Eski Domain | Yeni / Çalışan Domain | Onarım Sebebi |")
        report_lines.append("|---|---|---|")
        for r in repaired_sources:
            report_lines.append(f"| {r['domain']} | **{r.get('repaired_domain', '-')}** | {r['reason']} |")
        report_lines.append("")

    report_lines.append("## Neden Ölü? (Kurtarılamayan Sitelerin Analizi)\n")
    report_lines.append("| Domain | Durum | Teşhis Detayı |")
    report_lines.append("|---|---|---|")
    for r in sorted(dead_sources, key=lambda x: x["domain"]):
        report_lines.append(f"| {r['domain']} | `{r['status']}` | {r['reason'][:80]} |")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"\n[TAMAMLANDI] Teşhis ve Otomatik Tamirat Bitti ({elapsed:.1f}s):")
    print(f"  - Toplam Test: {len(target_sources)}")
    print(f"  - Canlı Kaynaklar: {len(alive_sources)}")
    print(f"  - Otomatik Onarılan: {len(repaired_sources)}")
    print(f"  - Ölü Kaynaklar: {len(dead_sources)}")
    print(f"  - Detaylı Rapor: {REPORT_FILE}")


if __name__ == "__main__":
    main()
