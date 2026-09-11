#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path("c:/Users/youruser/Documents/shuriken")
LEAKAGE_CSV = ROOT / "Reports/regression/deep_leakage_by_component.csv"

TARGET_BRANDS = ["Brand Three", "Brand One", "B2"]
HIGH_RISK = ["Ordering", "Payment", "Loyalty", "Account"]
REPLAY_MIN = {
    "Ordering": 20,
    "Payment": 16,
    "Loyalty/Rewards": 12,
    "Account": 8,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate zero-leak selector gates")
    parser.add_argument("--release", default="26.12", help="Release tag, e.g. 26.11")
    return parser.parse_args()


def read_csv(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc, errors="replace", newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    return []


def pass_fail(cond):
    return "PASS" if cond else "FAIL"


def main():
    args = parse_args()
    release_slug = args.release.replace(".", "_")
    pool_csv = ROOT / f"Reports/regression/{release_slug}_zero_leak_candidate_pool.csv"
    gaps_csv = ROOT / f"Reports/regression/{release_slug}_zero_leak_gaps.csv"
    out_csv = ROOT / f"Reports/regression/{release_slug}_zero_leak_gate_results.csv"

    pool = read_csv(pool_csv)
    gaps = read_csv(gaps_csv)
    leakage = read_csv(LEAKAGE_CSV)

    gate_rows = []

    # Gate 1: High-risk presence per brand in Tier1
    for brand in TARGET_BRANDS:
        b = [r for r in pool if r.get("brand") == brand and r.get("tier") == "TIER1"]
        areas = {r.get("area", "") for r in b}
        missing = [a for a in HIGH_RISK if a not in areas]
        ok = len(missing) == 0
        gate_rows.append({
            "gate": "Gate1_HighRiskPresence",
            "brand": brand,
            "status": pass_fail(ok),
            "blocker": "Yes" if not ok else "No",
            "details": "missing=" + ("|".join(missing) if missing else "none"),
        })

    # Gate 2: Scope-to-pool coverage
    for brand in TARGET_BRANDS:
        bg = [g for g in gaps if g.get("brand") == brand]
        uncovered = [g for g in bg if g.get("covered_in_candidate_pool") == "No"]
        ok = len(uncovered) == 0
        gate_rows.append({
            "gate": "Gate2_ScopeCoverage",
            "brand": brand,
            "status": pass_fail(ok),
            "blocker": "Yes" if not ok else "No",
            "details": f"uncovered_scope_issues={len(uncovered)}",
        })

    # Gate 3: Replay protection for repeat-offenders (global)
    area_counts = defaultdict(int)
    for r in pool:
        area_counts[r.get("area", "")] += 1

    for area, minimum in REPLAY_MIN.items():
        # map Loyalty/Rewards to selector area Loyalty
        selector_area = "Loyalty" if area == "Loyalty/Rewards" else area
        actual = area_counts.get(selector_area, 0)
        ok = actual >= minimum
        gate_rows.append({
            "gate": "Gate3_ReplayProtection",
            "brand": "ALL",
            "status": pass_fail(ok),
            "blocker": "Yes" if not ok else "No",
            "details": f"area={area};actual={actual};min={minimum}",
        })

    # Gate 4: Accessibility protection when accessibility exists in leakage
    leakage_access = [r for r in leakage if r.get("area") == "Accessibility"]
    need_access = len(leakage_access) > 0
    if need_access:
        for brand in TARGET_BRANDS:
            b_access = [r for r in pool if r.get("brand") == brand and r.get("area") == "Accessibility"]
            ok = len(b_access) >= 4
            gate_rows.append({
                "gate": "Gate4_AccessibilityProtection",
                "brand": brand,
                "status": pass_fail(ok),
                "blocker": "Yes" if not ok else "No",
                "details": f"access_tests={len(b_access)};min=4",
            })

    # Gate 5: Dedup integrity
    keys = [r.get("test_key", "") for r in pool]
    dup_count = len(keys) - len(set(keys))
    ok = dup_count == 0
    gate_rows.append({
        "gate": "Gate5_DedupIntegrity",
        "brand": "ALL",
        "status": pass_fail(ok),
        "blocker": "Yes" if not ok else "No",
        "details": f"duplicate_test_keys={dup_count}",
    })

    # Save
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["gate", "brand", "status", "blocker", "details"])
        w.writeheader()
        w.writerows(gate_rows)

    fails = [r for r in gate_rows if r["status"] == "FAIL"]
    blockers = [r for r in gate_rows if r["blocker"] == "Yes" and r["status"] == "FAIL"]

    print(f"Created: {out_csv}")
    print(f"Release: {args.release}")
    print(f"Gate checks: {len(gate_rows)} | Fails: {len(fails)} | Blockers: {len(blockers)}")
    for r in fails:
        print(f"  FAIL {r['gate']} [{r['brand']}] -> {r['details']}")


if __name__ == "__main__":
    main()
