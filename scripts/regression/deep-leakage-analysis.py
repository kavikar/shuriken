"""
deep-leakage-analysis.py

For releases 26.8-26.11 (tested releases), breaks down escaped defects by:
  - Platform (WEB, iOS, Android, mWeb, 3P)
  - Functional area (inferred from summary keywords)
  - Brand
  - Repeat offenders (same area escaped in multiple releases)

Outputs:
  - deep_leakage_by_component.csv
  - deep_leakage_repeat_offenders.csv
  - Console summary with actionable recommendations
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

DATA_DIR    = Path("c:/Users/youruser/Documents/shuriken/projects/jira/xray-regression-planner/data-csv-exports")
REPORTS_DIR = Path("c:/Users/youruser/Documents/shuriken/Reports/regression")
DEFECTS_CSV = DATA_DIR / "2026AllPRODDEFECTS.csv"
TP_CSV      = REPORTS_DIR / "historical_test_plans_all_releases.csv"

TESTED_RELEASES = {'26.8', '26.9', '26.10', '26.11'}

DOPS_RANGE_MAP = [
    (1301, 9999, '26.11'),
    (1113, 1300, '26.10'),
    (1052, 1112, '26.9'),
    (973,  1051, '26.8'),
    (846,   972, '26.7'),
    (726,   845, '26.6'),
    (642,   725, '26.5'),
    (547,   641, '26.4'),
    (139,   546, '26.3'),
]

# Functional area keyword mapping (order matters — first match wins)
FUNCTIONAL_AREAS = [
    ('Payment',          ['payment', 'pay ', 'checkout', 'credit card', 'wallet', 'apple pay', 'google pay', 'gift card']),
    ('Loyalty/Rewards',  ['loyalty', 'reward', 'points', 'check-in', 'checkin', 'earn', 'redeem', 'certificate']),
    ('Ordering',         ['order', 'cart', 'bag', 'combo', 'item', 'customiz', 'add to', 'place order']),
    ('Account',          ['login', 'sign in', 'sign-in', 'account', 'password', 'register', 'profile', 'session']),
    ('Location/Store',   ['location', 'store', 'pickup', 'delivery', 'restaurant', 'nearby', 'search']),
    ('Menu/PDP',         ['menu', 'pdp', 'product detail', 'calories', 'price', 'modifier', 'upsell']),
    ('Offers/Promotions',['offer', 'promo', 'coupon', 'discount', 'deal', 'bogo', 'free item']),
    ('Fulfillment',      ['fulfillment', 'fulfil', 'future order', 'asap', 'schedule', 'delivery time']),
    ('Notifications',    ['notification', 'push', 'alert', 'banner', 'toast', 'modal']),
    ('Accessibility',    ['wcag', 'accessibility', 'a11y', 'screen reader', 'aria']),
    ('Analytics/Tracking',['analytics', 'tracking', 'rokt', 'ads', 'splunk', 'event']),
    ('Performance',      ['performance', 'slow', 'timeout', 'latency', 'load time']),
    ('POS/Integration',  ['pos ', 'kiosk', 'integration', 'api', 'third.party', '3p ']),
]

PLATFORM_PATTERNS = [
    ('iOS',     ['[ios]', '[iphone]', 'ios ', '_ios', 'iphone', 'ipad', 'apple']),
    ('Android', ['[android]', '[aos]', 'android ', '_android', '_aos', 'aos ']),
    ('WEB',     ['[web]', '_web', 'web ', ' web]', 'webapp', 'desktop']),
    ('mWeb',    ['[mweb]', 'mweb', 'mobile web', 'mobile-web']),
    ('3P',      ['[3p]', 'third party', 'third-party', 'aggregator', 'marketplace']),
]

BRAND_PATTERNS = [
    ('Brand Two',   ['brand2', 'b2 ', '[b2]']),
    ('Brand Three', ['brand3', 'b3 ', '[b3]']),
    ('Brand One',   ['brand1', 'b1 ', '[b1]']),
    ('Brand Four',  ['brand4', 'b4 ', '[b4]']),
    ('GENERIC',   ['generic', 'multi-brand', 'multibrand', 'all brand']),
]

def read_csv_robust(path):
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with open(path, encoding=enc, errors='replace') as f:
                reader = csv.reader(f)
                headers = next(reader)
                return [dict(zip(headers, r)) for r in reader]
        except:
            continue
    return []

def get_release(row):
    fv = row.get('Fix versions', '').strip()
    ps = row.get('Parent summary', '').strip()
    key = row.get('Issue key', '')

    m = re.search(r'2[0-9]\.\d+(?:\.\d+)?', fv)
    if m: return m.group(0)
    m = re.search(r'2[0-9]\.\d+(?:\.\d+)?', ps)
    if m: return m.group(0)

    dm = re.match(r'DOPS-(\d+)', key)
    if dm:
        n = int(dm.group(1))
        for lo, hi, rel in DOPS_RANGE_MAP:
            if lo <= n <= hi:
                return rel
    return None

def classify(summary):
    sl = summary.lower()
    area = 'Other'
    for name, kws in FUNCTIONAL_AREAS:
        if any(k in sl for k in kws):
            area = name
            break
    platform = 'Unknown'
    for name, pats in PLATFORM_PATTERNS:
        if any(p in sl for p in pats):
            platform = name
            break
    brand = 'Multi/Unknown'
    for name, pats in BRAND_PATTERNS:
        if any(p in sl for p in pats):
            brand = name
            break
    return area, platform, brand

def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Deep Leakage Analysis — 26.8 to 26.11              ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    rows = read_csv_robust(DEFECTS_CSV)
    tp_rows = read_csv_robust(TP_CSV)

    # Build test coverage per release: set of test keys
    tp_by_release = defaultdict(set)
    for r in tp_rows:
        rel = r.get('release', '').strip()
        key = r.get('test_key', '').strip()
        if rel and key:
            tp_by_release[rel].add(key)

    # Also build coverage by summary keywords (crude but useful)
    tp_summaries_by_release = defaultdict(list)
    for r in tp_rows:
        rel = r.get('release', '').strip()
        summary = r.get('summary', '').lower()
        if rel and summary:
            tp_summaries_by_release[rel].append(summary)

    print(f"Test coverage: { {r: len(v) for r, v in tp_by_release.items()} }\n")

    # Filter to tested releases only
    escaped = []
    for row in rows:
        release = get_release(row)
        if release not in TESTED_RELEASES:
            continue
        summary = row.get('Summary', '')
        area, platform, brand = classify(summary)

        # Check if any test in that release covered same functional area
        tp_summaries = tp_summaries_by_release.get(release, [])
        area_kws = next((kws for name, kws in FUNCTIONAL_AREAS if name == area), [])
        was_area_tested = any(
            any(kw in ts for kw in area_kws)
            for ts in tp_summaries
        )

        escaped.append({
            'release':        release,
            'defect_key':     row.get('Issue key', ''),
            'summary':        summary[:80],
            'brand':          brand,
            'platform':       platform,
            'area':           area,
            'area_tested':    'Yes' if was_area_tested else 'No — GAP',
            'parent_summary': row.get('Parent summary', '')[:60],
        })

    print(f"Total false negatives (26.8–26.11): {len(escaped)}\n")

    # ── By functional area ──────────────────────────────────────────
    area_counts = defaultdict(lambda: defaultdict(int))
    for e in escaped:
        area_counts[e['area']][e['release']] += 1

    area_total = {a: sum(v.values()) for a, v in area_counts.items()}

    print("═" * 70)
    print("BY FUNCTIONAL AREA (across tested releases)")
    print("═" * 70)
    print(f"{'Area':<25} {'Total':>6}  {'26.8':>6} {'26.9':>6} {'26.10':>6} {'26.11':>6}  Verdict")
    print("─" * 70)
    for area, total in sorted(area_total.items(), key=lambda x: -x[1]):
        r8  = area_counts[area].get('26.8',  0)
        r9  = area_counts[area].get('26.9',  0)
        r10 = area_counts[area].get('26.10', 0)
        r11 = area_counts[area].get('26.11', 0)
        releases_affected = sum(1 for x in [r8,r9,r10,r11] if x > 0)
        verdict = "🔴 REPEAT OFFENDER" if releases_affected >= 3 else ("🟡 Recurring" if releases_affected == 2 else "")
        print(f"  {area:<23} {total:>6}  {r8:>6} {r9:>6} {r10:>6} {r11:>6}  {verdict}")

    # ── By platform ─────────────────────────────────────────────────
    print()
    print("═" * 70)
    print("BY PLATFORM")
    print("═" * 70)
    plat_counts = defaultdict(int)
    for e in escaped:
        plat_counts[e['platform']] += 1
    for plat, cnt in sorted(plat_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(escaped) * 100
        print(f"  {plat:<15} {cnt:>5} ({pct:.0f}%)")

    # ── By brand ────────────────────────────────────────────────────
    print()
    print("═" * 70)
    print("BY BRAND")
    print("═" * 70)
    brand_counts = defaultdict(int)
    for e in escaped:
        brand_counts[e['brand']] += 1
    for brand, cnt in sorted(brand_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(escaped) * 100
        print(f"  {brand:<20} {cnt:>5} ({pct:.0f}%)")

    # ── Areas tested but still leaked ───────────────────────────────
    print()
    print("═" * 70)
    print("AREAS THAT HAD TEST COVERAGE BUT STILL LEAKED (True False Negatives)")
    print("═" * 70)
    fn_areas = defaultdict(int)
    for e in escaped:
        if e['area_tested'] == 'Yes':
            fn_areas[e['area']] += 1
    for area, cnt in sorted(fn_areas.items(), key=lambda x: -x[1]):
        print(f"  {area:<25} {cnt:>4} defects leaked despite test coverage → needs stronger test cases")

    # ── Areas with NO test coverage at all ──────────────────────────
    print()
    print("═" * 70)
    print("AREAS WITH ZERO TEST COVERAGE (Pure Coverage Gaps in tested releases)")
    print("═" * 70)
    gap_areas = defaultdict(int)
    for e in escaped:
        if e['area_tested'] == 'No — GAP':
            gap_areas[e['area']] += 1
    for area, cnt in sorted(gap_areas.items(), key=lambda x: -x[1]):
        print(f"  {area:<25} {cnt:>4} defects with no test coverage → ADD TESTS")

    # ── Recommendations ─────────────────────────────────────────────
    print()
    print("═" * 70)
    print("RECOMMENDATIONS FOR 26.12")
    print("═" * 70)
    top_areas = sorted(area_total.items(), key=lambda x: -x[1])[:5]
    for i, (area, total) in enumerate(top_areas, 1):
        releases_affected = sum(1 for r in ['26.8','26.9','26.10','26.11'] if area_counts[area].get(r,0) > 0)
        action = "INCREASE test depth + add negative/edge cases" if fn_areas.get(area,0) > 0 else "ADD test cases — no coverage exists"
        print(f"  {i}. {area} ({total} escapes, {releases_affected}/4 releases): {action}")

    # ── Save CSV ─────────────────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "deep_leakage_false_negatives.csv"
    with open(out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(escaped[0].keys()))
        writer.writeheader()
        writer.writerows(sorted(escaped, key=lambda x: (x['area'], x['release'])))

    # Save by-component summary
    out2 = REPORTS_DIR / "deep_leakage_by_component.csv"
    with open(out2, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['area', 'total', '26.8', '26.9', '26.10', '26.11', 'repeat_offender', 'has_test_coverage'])
        for area, total in sorted(area_total.items(), key=lambda x: -x[1]):
            r8  = area_counts[area].get('26.8', 0)
            r9  = area_counts[area].get('26.9', 0)
            r10 = area_counts[area].get('26.10', 0)
            r11 = area_counts[area].get('26.11', 0)
            releases_hit = sum(1 for x in [r8,r9,r10,r11] if x > 0)
            repeat = 'Yes' if releases_hit >= 3 else ('Partial' if releases_hit == 2 else 'No')
            has_coverage = 'Yes' if fn_areas.get(area, 0) > 0 else 'No'
            writer.writerow([area, total, r8, r9, r10, r11, repeat, has_coverage])

    print(f"\n✓ Saved: {out}")
    print(f"✓ Saved: {out2}")

if __name__ == '__main__':
    main()
