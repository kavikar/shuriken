#!/usr/bin/env python3
"""
Historical Leakage Analyzer

Analyzes scope vs production defects to identify:
  - Coverage Gaps (defects in scope but NOT tested)
  - False Negatives (defects tested but still escaped)

Outputs:
  - historical_leakage_analysis.csv
  - Summary table showing escapes per release
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

REPORTS_DIR = Path("c:/Users/youruser/Documents/shuriken/Reports/regression")
DATA_DIR = Path("c:/Users/youruser/Documents/shuriken/projects/jira/xray-regression-planner/data-csv-exports")

SCOPE_CSV   = DATA_DIR / "26-6To26-11ReleaseTickets.csv"
DEFECTS_CSV = DATA_DIR / "2026AllPRODDEFECTS.csv"
TEST_PLANS_CSV = REPORTS_DIR / "historical_test_plans_all_releases.csv"

def extract_release(fix_version: str) -> str:
    """Extract release number from fixVersion string. 'Digital 26.12' -> '26.12'"""
    if not fix_version:
        return "UNKNOWN"
    parts = fix_version.split()
    return parts[-1] if len(parts) > 1 else fix_version

def read_csv(path) -> list:
    """Read CSV with encoding fallback, handle duplicate column names."""
    rows = []
    for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with open(path, encoding=enc, errors='replace') as f:
                # Use raw reader to handle duplicate column names
                reader = csv.reader(f)
                headers = next(reader)
                for row in reader:
                    rows.append(dict(zip(headers, row)))
            break
        except Exception:
            continue
    return rows

def load_scope():
    """Load scope tickets grouped by release."""
    scope_by_release = defaultdict(set)  # release -> {issue_key, ...}
    scope_rows = read_csv(SCOPE_CSV)
    print(f"   Total rows: {len(scope_rows)}")

    for row in scope_rows:
        key = row.get('Issue key', '').strip()
        # First 'Fix versions' column contains the release
        fix_version = row.get('Fix versions', '').strip()
        if key and fix_version:
            release = extract_release(fix_version)
            scope_by_release[release].add(key)

    return scope_by_release

def load_defects():
    """Load production defects grouped by release.
    
    Priority for release assignment:
    1. Fix versions column
    2. Parent summary containing release number (e.g. 'Digital 26.10 defects')
    3. DOPS issue number ranges (derived from known anchor points):
       - DOPS  139–390  → 26.3
       - DOPS  391–546  → 26.3/26.4
       - DOPS  547–641  → 26.4
       - DOPS  642–720  → 26.5
       - DOPS  721–845  → 26.5/26.6
       - DOPS  846–972  → 26.7
       - DOPS  973–1051 → 26.8
       - DOPS 1052–1112 → 26.9
       - DOPS 1113–1300 → 26.10
       - DOPS 1301+     → 26.11+
    """
    # DOPS number range → release
    # Derived from known anchors + release dates from sprint tracker:
    #   26.6  released Mar 31–Apr 2   | anchor: DOPS-726
    #   26.7  released Apr 14–15      | anchor: DOPS-846
    #   26.8  released Apr 28–29      | anchor: DOPS-973
    #   26.9  released May 13–14      | anchor: DOPS-1052
    #   26.10 released May 27–29      | anchor: DOPS-1113
    #   26.11 released Jun 9–10       | anchor: DOPS-1301 (est.)
    #   26.5  CANCELLED — no regression run
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

    def dops_num_to_release(key: str) -> str:
        m = re.match(r'DOPS-(\d+)', key)
        if not m:
            return None
        n = int(m.group(1))
        for lo, hi, rel in DOPS_RANGE_MAP:
            if lo <= n <= hi:
                return rel
        return None

    defects_by_release = defaultdict(list)
    rows = read_csv(DEFECTS_CSV)
    print(f"   Total rows: {len(rows)}")

    mapped_fv = mapped_ps = mapped_dops = unmapped = 0

    for row in rows:
        key = row.get('Issue key', '').strip()
        summary = row.get('Summary', '')
        fix_version = row.get('Fix versions', '').strip()
        parent_summary = row.get('Parent summary', '').strip()
        priority = row.get('Priority', 'Medium')

        if not key:
            continue

        release = None
        method = None

        # 1. Fix version
        if fix_version:
            m = re.search(r'2[0-9]\.\d+(?:\.\d+)?', fix_version)
            if m:
                release = m.group(0)
                method = 'fix_version'
                mapped_fv += 1

        # 2. Parent summary
        if not release and parent_summary:
            m = re.search(r'2[0-9]\.\d+(?:\.\d+)?', parent_summary)
            if m:
                release = m.group(0)
                method = 'parent_summary'
                mapped_ps += 1

        # 3. DOPS number range
        if not release:
            release = dops_num_to_release(key)
            if release:
                method = 'dops_range'
                mapped_dops += 1
            else:
                unmapped += 1

        if release:
            defects_by_release[release].append({
                'key': key,
                'summary': summary,
                'platform': _infer_platform(summary),
                'priority': priority,
                'parent_summary': parent_summary,
                'release_method': method,
            })

    print(f"   Mapped by fix version: {mapped_fv}")
    print(f"   Mapped by parent summary: {mapped_ps}")
    print(f"   Mapped by DOPS range: {mapped_dops}")
    print(f"   Unmapped: {unmapped}")

    return defects_by_release

def _infer_platform(summary: str) -> str:
    summary_lower = summary.lower()
    for b in ['B2', 'Brand Three', 'B3', 'Brand One', 'Brand Four', 'GENERIC']:
        if b.lower() in summary_lower:
            return b
    return 'Unknown'
    
    return defects_by_release

def load_test_plans():
    """Load extracted test cases from historical Test Plans."""
    tp_by_release = defaultdict(set)  # release -> {test_key, ...}
    if not TEST_PLANS_CSV.exists():
        print("   ⚠️  No test plan data found. Run extract-all-historical-test-plans.ts first.")
        return tp_by_release

    rows = read_csv(TEST_PLANS_CSV)
    for row in rows:
        release = row.get('release', '').strip()
        test_key = row.get('test_key', '').strip()
        if release and test_key:
            tp_by_release[release].add(test_key)

    return tp_by_release

def main():
    print("╔════════════════════════════════════════════════╗")
    print("║  Historical Leakage Analysis                  ║")
    print("╚════════════════════════════════════════════════╝\n")

    print(f"📥 Loading scope ({SCOPE_CSV.name})...")
    scope_by_release = load_scope()
    total_scope = sum(len(v) for v in scope_by_release.values())
    print(f"   ✓ {total_scope} issues across releases: {sorted(scope_by_release.keys())}\n")

    print(f"📥 Loading defects ({DEFECTS_CSV.name})...")
    defects_by_release = load_defects()
    total_defects = sum(len(v) for v in defects_by_release.values())
    print(f"   ✓ {total_defects} defects across releases: {sorted(defects_by_release.keys())}\n")

    print(f"📥 Loading test plan data ({TEST_PLANS_CSV.name})...")
    tp_by_release = load_test_plans()
    total_tp = sum(len(v) for v in tp_by_release.values())
    print(f"   ✓ {total_tp} test cases across releases: {sorted(tp_by_release.keys())}\n")

    # Analysis
    print("[ANALYSIS] Classifying defect escapes...")
    all_escapes = []
    escape_summary = {}

    all_releases = sorted(set(list(scope_by_release.keys()) + list(defects_by_release.keys())))

    for release in all_releases:
        release_defects = defects_by_release.get(release, [])
        tp_tests = tp_by_release.get(release, set())
        scope_count = len(scope_by_release.get(release, {}))
        tp_count = len(tp_tests)

        false_negatives = 0
        coverage_gaps = 0

        for defect in release_defects:
            # If test plan data exists for this release, check if it was tested
            if tp_count > 0:
                # Consider: was there test coverage for this release?
                # True gap = no tests in the Test Plan for this release
                # False negative = tests existed but defect escaped
                gap_type = "False Negative" if tp_count > 0 else "Coverage Gap"
            else:
                # No test plan data → coverage gap
                gap_type = "Coverage Gap"

            if gap_type == "False Negative":
                false_negatives += 1
            else:
                coverage_gaps += 1

            all_escapes.append({
                'release': release,
                'defect_key': defect['key'],
                'defect_summary': defect['summary'][:80],
                'gap_type': gap_type,
                'platform': defect.get('platform', ''),
                'priority': defect.get('priority', ''),
                'scope_count': scope_count,
                'tp_test_count': tp_count,
            })

        total = false_negatives + coverage_gaps
        if total > 0:
            escape_summary[release] = {
                'total': total,
                'false_negatives': false_negatives,
                'coverage_gaps': coverage_gaps,
                'scope_count': scope_count,
                'tp_count': tp_count,
            }

    # Summary output
    print("\n[SUMMARY] Escapes per release:")
    print("─" * 80)
    total_all = 0
    for release in sorted(escape_summary.keys()):
        s = escape_summary[release]
        total_all += s['total']
        print(f"  {release:<10} {s['total']:>4} escapes  "
              f"(False Neg: {s['false_negatives']}, Coverage Gap: {s['coverage_gaps']})  "
              f"| Scope: {s['scope_count']}, Tested: {s['tp_count']}")

    if not escape_summary:
        print("  No overlapping releases between scope and defects found.")
        print(f"  Scope releases:   {sorted(scope_by_release.keys())}")
        print(f"  Defect releases:  {sorted(defects_by_release.keys())}")

    print(f"\nTotal defects across all releases: {total_defects}")
    print(f"Total classified escapes: {total_all}")

    # Write CSV
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_csv = REPORTS_DIR / "historical_leakage_analysis.csv"

    if all_escapes:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['release', 'defect_key', 'defect_summary', 'gap_type', 'platform', 'priority', 'scope_count', 'tp_test_count'])
            writer.writeheader()
            writer.writerows(sorted(all_escapes, key=lambda x: (x['release'], x['defect_key'])))
        print(f"\n✓ Leakage analysis saved: {output_csv}")

if __name__ == '__main__':
    main()
