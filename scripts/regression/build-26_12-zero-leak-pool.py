#!/usr/bin/env python3
import argparse
import csv
import json
import glob
from collections import defaultdict
from pathlib import Path

ROOT = Path("c:/Users/youruser/Documents/shuriken")
SCOPE_CSV = ROOT / "projects/jira/xray-regression-planner/data-csv-exports/Digital 26.12 Release candidates (Jira).csv"
HIST_CSV = ROOT / "Reports/regression/historical_test_plans_all_releases.csv"
BRAND3_DIR = ROOT / "Reports/regression/brand3_sets"
OUT_DIR = ROOT / "Reports/regression"

TARGET_BRANDS = ["Brand Three", "Brand One", "B2"]
RISK_AREAS = ["Offers", "Loyalty", "Ordering", "Payment", "Account", "Location", "Menu", "Accessibility", "Analytics"]
AREA_KEYWORDS = {
    "Ordering": ["order", "bag", "checkout", "combo", "modifier", "reorder", "add to bag"],
    "Payment": ["payment", "card", "wallet", "gift card", "tally", "checkout", "refund"],
    "Loyalty": ["loyalty", "reward", "points", "check-in", "redeem"],
    "Offers": ["offer", "promo", "discount", "coupon", "deal", "certificate"],
    "Account": ["login", "sign in", "auth", "password", "otp", "profile", "account"],
    "Location": ["location", "store", "pickup", "delivery", "address", "recent"],
    "Menu": ["menu", "pdp", "plp", "modifier", "price", "calorie"],
    "Accessibility": ["accessibility", "wcag", "a11y", "alt text", "skip link"],
    "Analytics": ["analytics", "event", "ga4", "splunk", "tracking", "rokt"],
}


def read_csv(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, encoding=enc, errors="replace", newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    return []


def detect_brand(text):
    t = (text or "").lower()
    if "brand3" in t or "[b3" in t or " s nc" in t or " b3" in t:
        return "Brand Three"
    if "brand1" in t or "[b1" in t:
        return "Brand One"
    if "b2" in t or "wings" in t:
        return "B2"
    return "Other"


def detect_area(text, components=""):
    summary = (text or "").lower()
    z = f"{summary} {components or ''}".lower()
    if any(k in summary for k in AREA_KEYWORDS["Offers"]):
        return "Offers"
    for area in RISK_AREAS:
        if area == "Offers":
            continue
        if any(k in z for k in AREA_KEYWORDS[area]):
            return area
    return "Other"


def score_test(summary, components):
    s = 0
    z = f"{summary} {components}".lower()
    if any(k in z for k in AREA_KEYWORDS["Ordering"]):
        s += 5
    if any(k in z for k in AREA_KEYWORDS["Payment"]):
        s += 5
    if any(k in z for k in AREA_KEYWORDS["Offers"]):
        s += 4
    if any(k in z for k in AREA_KEYWORDS["Loyalty"]):
        s += 5
    if any(k in z for k in AREA_KEYWORDS["Account"]):
        s += 3
    if any(k in z for k in AREA_KEYWORDS["Accessibility"]):
        s += 3
    if any(k in z for k in AREA_KEYWORDS["Analytics"]):
        s += 2
    return s


def parse_args():
    parser = argparse.ArgumentParser(description="Build zero-leak candidate pool for a release")
    parser.add_argument("--release", default="26.12", help="Release tag, e.g. 26.11")
    parser.add_argument("--scope-csv", default=str(SCOPE_CSV), help="Path to scope CSV")
    return parser.parse_args()


def load_scope_by_brand(scope_csv_path):
    rows = read_csv(Path(scope_csv_path))
    out = []
    by_brand = defaultdict(list)
    for r in rows:
        summary = r.get("Summary", "")
        labels = " ".join([v for k, v in r.items() if k.startswith("Labels") and v])
        brand = detect_brand(summary + " " + labels)
        area = detect_area(summary, labels)
        issue = {
            "issue_key": r.get("Issue key", ""),
            "summary": summary,
            "brand": brand,
            "area": area,
            "status": r.get("Status", ""),
        }
        out.append(issue)
        by_brand[brand].append(issue)
    return out, by_brand


def load_brand3_tests():
    tests = []
    for f in glob.glob(str(BRAND3_DIR / "TE-*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
            source = Path(f).stem
            for t in data.get("tests", []):
                summary = t.get("summary", "")
                comps = "|".join(t.get("components", []))
                tests.append({
                    "brand": "Brand Three",
                    "source": f"Brand3TestSet:{source}",
                    "release_origin": "Current Jira Test Sets",
                    "test_key": t.get("key", ""),
                    "summary": summary,
                    "components": comps,
                    "area": detect_area(summary, comps),
                    "score": score_test(summary, comps),
                })
        except Exception:
            continue
    return tests


def load_hist_brand_tests():
    rows = read_csv(HIST_CSV)
    selected = []
    for r in rows:
        rel = r.get("release", "")
        if rel not in {"26.9", "26.10", "26.11"}:
            continue
        summary = r.get("summary", "")
        comps = r.get("components", "")
        brand = detect_brand(summary + " " + comps)
        if brand not in {"Brand One", "B2"}:
            continue
        selected.append({
            "brand": brand,
            "source": f"HistoricalTP:{r.get('tp_key','')}",
            "release_origin": rel,
            "test_key": r.get("test_key", ""),
            "summary": summary,
            "components": comps,
            "area": detect_area(summary, comps),
            "score": score_test(summary, comps),
        })
    return selected


def pick_brand_pool(brand, tests, scope_count):
    # capacity tuned for zero leak: deeper than normal
    cap = 180 if brand == "Brand Three" else 220
    cap += min(80, scope_count * 2)

    # prioritize high-risk areas and unique tests
    tests = sorted(tests, key=lambda x: (-x["score"], x["area"], x["test_key"]))
    chosen = []
    seen = set()
    area_quota = {
        "Ordering": 0.24,
        "Payment": 0.20,
        "Loyalty": 0.16,
        "Account": 0.12,
        "Location": 0.10,
        "Menu": 0.08,
        "Accessibility": 0.06,
        "Offers": 0.03,
        "Analytics": 0.01,
    }
    buckets = defaultdict(list)
    for t in tests:
        buckets[t["area"]].append(t)

    for area, pct in area_quota.items():
        target = max(1, int(cap * pct))
        for t in buckets.get(area, []):
            if len([x for x in chosen if x["area"] == area]) >= target:
                break
            if t["test_key"] in seen:
                continue
            chosen.append(t)
            seen.add(t["test_key"])

    # fill remaining by score
    if len(chosen) < cap:
        for t in tests:
            if t["test_key"] in seen:
                continue
            chosen.append(t)
            seen.add(t["test_key"])
            if len(chosen) >= cap:
                break

    # assign tier suggestion
    for t in chosen:
        if t["area"] in {"Ordering", "Payment", "Loyalty", "Account"}:
            t["tier"] = "TIER1"
        elif t["area"] in {"Location", "Menu", "Accessibility", "Offers"}:
            t["tier"] = "TIER2"
        else:
            t["tier"] = "TIER3"
    return chosen


def main():
    args = parse_args()
    release_slug = args.release.replace(".", "_")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    scope_rows, scope_by_brand = load_scope_by_brand(args.scope_csv)
    brand3_tests = load_brand3_tests()
    hist_tests = load_hist_brand_tests()

    pool = []
    for brand in TARGET_BRANDS:
        if brand == "Brand Three":
            brand_tests = brand3_tests
        else:
            brand_tests = [t for t in hist_tests if t["brand"] == brand]
        picked = pick_brand_pool(brand, brand_tests, len(scope_by_brand.get(brand, [])))
        pool.extend(picked)

    # write candidate pool
    candidate_csv = OUT_DIR / f"{release_slug}_zero_leak_candidate_pool.csv"
    with open(candidate_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["brand", "tier", "area", "score", "source", "release_origin", "test_key", "summary", "components"])
        for t in sorted(pool, key=lambda x: (x["brand"], x["tier"], -x["score"], x["test_key"])):
            w.writerow([t["brand"], t["tier"], t["area"], t["score"], t["source"], t["release_origin"], t["test_key"], t["summary"], t["components"]])

    # summary
    summary_csv = OUT_DIR / f"{release_slug}_zero_leak_plan_summary.csv"
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["brand", "scope_items", "candidate_tests", "tier1", "tier2", "tier3", "ordering", "payment", "loyalty", "account", "accessibility"])
        for brand in TARGET_BRANDS:
            b = [t for t in pool if t["brand"] == brand]
            w.writerow([
                brand,
                len(scope_by_brand.get(brand, [])),
                len(b),
                len([x for x in b if x["tier"] == "TIER1"]),
                len([x for x in b if x["tier"] == "TIER2"]),
                len([x for x in b if x["tier"] == "TIER3"]),
                len([x for x in b if x["area"] == "Ordering"]),
                len([x for x in b if x["area"] == "Payment"]),
                len([x for x in b if x["area"] == "Loyalty"]),
                len([x for x in b if x["area"] == "Account"]),
                len([x for x in b if x["area"] == "Accessibility"]),
            ])

    # gap report: scope areas not represented in brand pool
    gaps_csv = OUT_DIR / f"{release_slug}_zero_leak_gaps.csv"
    with open(gaps_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["brand", "scope_issue_key", "scope_area", "scope_summary", "covered_in_candidate_pool"])
        for brand, issues in scope_by_brand.items():
            if brand not in TARGET_BRANDS:
                continue
            brand_areas = {t["area"] for t in pool if t["brand"] == brand}
            for i in issues:
                covered = "Yes" if i["area"] in brand_areas else "No"
                w.writerow([brand, i["issue_key"], i["area"], i["summary"], covered])

    print(f"Created: {candidate_csv}")
    print(f"Created: {summary_csv}")
    print(f"Created: {gaps_csv}")
    print(f"Release: {args.release}")
    print(f"Scope file: {args.scope_csv}")
    print(f"Pool total: {len(pool)}")
    print(f"Brand Three source tests: {len(brand3_tests)}")
    print(f"brand1/B2 historical source tests: {len(hist_tests)}")


if __name__ == "__main__":
    main()
