#!/usr/bin/env python3
"""Tum asamalarin (0: envanter, 1: HTTP taramasi, 2: bolum/gorsel zinciri, 3: onarim denemesi)
sonucunu birlestirip sources/tr/TRIAGE_REPORT.md uretir.

Kullanim: python scripts/triage_report.py
Girdi: data/triage.json, data/triage_stage1.json, data/triage_stage2.json, data/triage_stage3.json (varsa)
Cikti: sources/tr/TRIAGE_REPORT.md
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE_DIR, "data")
OUT_PATH = os.path.join(BASE_DIR, "sources", "tr", "TRIAGE_REPORT.md")


def load(name, default=None):
    path = os.path.join(DATA, name)
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def final_verdict(domain, s1, s2, s3_by_domain, verified_working):
    r1 = s1.get(domain, {}) if s1 else {}
    r2 = s2.get(domain, {}) if s2 else {}
    r3 = s3_by_domain.get(domain)

    if r1.get("stage1") == "unverified_local":
        if verified_working:
            return "kullanici-dogruladi-yerelden-erisilemedi", "kullanici elle calistigini dogruladi; bu makineden erisim yok"
        return "yerelden-dogrulanamadi", "CI'da (_test.yml) dogrulanmali"
    if r2.get("stage2") == "pass":
        return "saglikli", r2.get("reason", "")
    if r2.get("stage2") in ("fail", "selector_broken"):
        if verified_working:
            # Kullanici bu kaynagin calistigini elle dogruladi (Kototoro export). Otomatik test
            # "fail" diyorsa, bu testin kendi heuristiginin (link bulma vb.) o site yapisina
            # uymadigini gosterir - kaynagin kendisi kirik degil. Onarim denemesi atlanir.
            return "kullanici-dogruladi-test-yanlis-negatif", f"otomatik test '{r2.get('reason','')}' dedi ama kullanici calistigini dogruladi"
        if r3:
            if r3.get("repaired"):
                return "onarildi", r3.get("reason", "")
            return "onarilamadi", r3.get("reason", "manuel inceleme gerekli")
        return "kirik-test-edilmedi-onarim", r2.get("reason", "")
    if r2.get("stage2") == "skip":
        return "test-edilemedi", r2.get("reason", "")
    if r1.get("stage1") == "fail":
        if verified_working:
            return "kullanici-dogruladi-test-yanlis-negatif", f"otomatik test '{r1.get('reason','')}' dedi ama kullanici calistigini dogruladi"
        return "kirik", r1.get("reason", "")
    return "bilinmiyor", ""


def main():
    triage = load("triage.json", {"entries": []})
    s1 = (load("triage_stage1.json", {}) or {}).get("results", {})
    s2 = (load("triage_stage2.json", {}) or {}).get("results", {})
    s3 = load("triage_stage3.json", {}) or {}
    s3_by_domain = {r["domain"]: r for r in s3.get("results", [])}
    manual_review = {r["domain"]: r for r in s3.get("manual_review", [])}

    sources_path = os.path.join(BASE_DIR, "sources", "tr", "sources.json")
    verified_domains = set()
    if os.path.isfile(sources_path):
        with open(sources_path, encoding="utf-8") as fh:
            for s in json.load(fh).get("sources", []):
                if s.get("verifiedWorkingByUser"):
                    verified_domains.add(s["domain"])

    rows = []
    for e in triage["entries"]:
        domain = e["domain"]
        verified = domain in verified_domains
        verdict, detail = final_verdict(domain, s1, s2, s3_by_domain, verified)
        if domain in manual_review and verdict not in ("saglikli",) and not verified:
            verdict = "manuel-inceleme"
            detail = manual_review[domain]["reason"]
        rows.append({"domain": domain, "name": e.get("name"), "kind": e["kind"],
                      "engine": e.get("engine") or "-", "verdict": verdict, "detail": detail})

    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    lines = []
    lines.append("# TR kaynaklari - kademeli test ve onarim raporu\n")
    lines.append("Bu rapor `scripts/triage.py` -> `test_stage1.py` -> `test_stage2.py` -> "
                  "`repair_stage3.mjs` zincirinin ciktisidir. Her asama, oncekini gecemeyenlere "
                  "uygulanir; `saglikli` olanlar liste+bolum+gorsel zincirini gercekten gecmistir "
                  "(sadece liste sayfasinda motor markeri bulunmasi yeterli sayilmaz).\n")
    lines.append("## Ozet\n")
    lines.append("| Durum | Adet | Aciklama |")
    lines.append("|---|---|---|")
    desc = {
        "saglikli": "liste -> detay -> bolum -> gorsel zinciri gercekten calisti",
        "onarildi": "selector kirikti, otomatik yeniden uretim + statik HTML dogrulamasiyla onarildi",
        "onarilamadi": "selector kirik, otomatik onarim denendi ama basarisiz (manuel bakilmali)",
        "manuel-inceleme": "upstream/override parser kirik; otomatik kod yamasi guvenilir degil",
        "kirik": "liste sayfasi erisilebilir ama motor markeri/bolum/gorsel bulunamadi",
        "test-edilemedi": "zincirin bir adiminda site HTTP hatasi/baglanti sorunu verdi",
        "yerelden-dogrulanamadi": "bu makineden/agdan domaine hic baglanilamadi (CI'da farkli IP ile dogrulanmali)",
        "kirik-test-edilmedi-onarim": "kirik tespit edildi ama stage3 onarimi bu kayit icin calistirilmadi",
        "kullanici-dogruladi-test-yanlis-negatif": "kullanici Kototoro'da elle calistigini dogruladi; otomatik test heuristigi bu site yapisina uymadi (YANLIS-NEGATIF, kaynak kirik degil)",
        "kullanici-dogruladi-yerelden-erisilemedi": "kullanici elle calistigini dogruladi; bu makineden erisim engellendigi icin otomatik test calisamadi",
        "bilinmiyor": "siniflandirilamadi",
    }
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} | {desc.get(k, '-')} |")
    lines.append("")

    lines.append("## Onarilan kaynaklar\n")
    repaired = [r for r in rows if r["verdict"] == "onarildi"]
    if repaired:
        lines.append("| Domain | Detay |")
        lines.append("|---|---|")
        for r in repaired:
            lines.append(f"| {r['domain']} | {r['detail']} |")
    else:
        lines.append("_Bu calismada otomatik onarilan kaynak yok._")
    lines.append("")

    lines.append("## Manuel inceleme gereken kaynaklar\n")
    lines.append("Upstream/override parser'lar: base-class parametreli yapidan dolayi otomatik "
                 "selector yamasi guvenilir degil, elle bakilmali.\n")
    manual = [r for r in rows if r["verdict"] == "manuel-inceleme"]
    if manual:
        lines.append("| Domain | Motor | Detay |")
        lines.append("|---|---|---|")
        for r in manual:
            lines.append(f"| {r['domain']} | {r['engine']} | {r['detail']} |")
    else:
        lines.append("_Yok._")
    lines.append("")

    lines.append("## Hala kirik (onarilamadi veya test edilemedi)\n")
    lines.append("| Domain | Motor | Durum | Detay |")
    lines.append("|---|---|---|---|")
    broken = [r for r in rows if r["verdict"] in
              ("onarilamadi", "kirik", "test-edilemedi", "kirik-test-edilmedi-onarim")]
    for r in sorted(broken, key=lambda x: x["domain"]):
        lines.append(f"| {r['domain']} | {r['engine']} | {r['verdict']} | {r['detail'][:100]} |")
    lines.append("")

    lines.append("## Yerelden dogrulanamayan (CI'da kontrol edilmeli)\n")
    unverified = [r for r in rows if r["verdict"] == "yerelden-dogrulanamadi"]
    lines.append(f"{len(unverified)} domain bu makineden/agdan hic erisilemedi "
                 "(SSL/baglanti reddi - site tarafi degil, yerel ag kisitlamasi olasi). "
                 "`gh workflow run _test.yml` ile CI'da gercek sonuc alinmali.\n")

    lines.append("## Kullanici tarafindan dogrulanan ama otomatik testin yanildigi kaynaklar\n")
    lines.append("Bu domainler `sources/tr/verified_working_kototoro_export.json` (kullanicinin Kototoro'dan "
                 "elle test edip export ettigi grup) icinde yer alir - kullanici gercekten calistigini "
                 "dogruladi. Otomatik test bunlari 'fail'/'unverified_local' derse, bu testin kendi "
                 "heuristiginin (link bulma, yerel ag erisimi) yetersizligidir, kaynagin kendisi degil.\n")
    uv_fail = [r for r in rows if r["verdict"] == "kullanici-dogruladi-test-yanlis-negatif"]
    uv_local = [r for r in rows if r["verdict"] == "kullanici-dogruladi-yerelden-erisilemedi"]
    if uv_fail:
        lines.append("**Test yanlis-negatif uretti (site erisilebilir ama heuristik link/selector bulamadi):**\n")
        lines.append("| Domain | Motor |")
        lines.append("|---|---|")
        for r in sorted(uv_fail, key=lambda x: x["domain"]):
            lines.append(f"| {r['domain']} | {r['engine']} |")
        lines.append("")
    if uv_local:
        lines.append("**Yerelden hic erisilemedi (CI'da dogrulanmali, test heuristigiyle alakasiz):**\n")
        lines.append("| Domain | Motor |")
        lines.append("|---|---|")
        for r in sorted(uv_local, key=lambda x: x["domain"]):
            lines.append(f"| {r['domain']} | {r['engine']} |")
        lines.append("")

    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"Output: {OUT_PATH}")
    print(f"  counts={counts}")


if __name__ == "__main__":
    main()
