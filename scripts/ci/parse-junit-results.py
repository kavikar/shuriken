#!/usr/bin/env python3
"""
Shuriken — Parse JUnit XML results into a summary JSON.
Used by GitLab CI to feed data into Confluence report and notifications.
"""

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def parse_junit(xml_path: str) -> dict:
    """Parse JUnit XML and return structured results."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Handle both <testsuites> and <testsuite> root
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    else:
        suites = [root]

    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "duration_s": 0.0,
        "tests": [],
    }

    for suite in suites:
        results["total"] += int(suite.get("tests", 0))
        results["failed"] += int(suite.get("failures", 0))
        results["errors"] += int(suite.get("errors", 0))
        results["skipped"] += int(suite.get("skipped", 0))
        results["duration_s"] += float(suite.get("time", 0))

        for tc in suite.findall("testcase"):
            test = {
                "name": tc.get("name", "unknown"),
                "classname": tc.get("classname", ""),
                "duration_s": float(tc.get("time", 0)),
                "status": "passed",
                "message": None,
            }

            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")

            if failure is not None:
                test["status"] = "failed"
                test["message"] = failure.get("message", failure.text or "")
            elif error is not None:
                test["status"] = "error"
                test["message"] = error.get("message", error.text or "")
            elif skipped is not None:
                test["status"] = "skipped"
                test["message"] = skipped.get("message", "")

            results["tests"].append(test)

    results["passed"] = results["total"] - results["failed"] - results["errors"] - results["skipped"]
    return results


def main():
    parser = argparse.ArgumentParser(description="Parse JUnit XML → summary JSON")
    parser.add_argument("--input", required=True, help="JUnit XML file path")
    parser.add_argument("--brand", required=True, help="Brand name (brand3/brand1/b2)")
    parser.add_argument("--version", default="unknown", help="Build version")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        # No results file — create a failure summary
        summary = {
            "brand": args.brand,
            "buildVersion": args.version,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 1,
            "duration_s": 0,
            "status": "error",
            "tests": [],
            "message": f"No JUnit results file found at {args.input}",
        }
    else:
        results = parse_junit(str(input_path))
        summary = {
            "brand": args.brand,
            "buildVersion": args.version,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **results,
            "status": "passed" if results["failed"] == 0 and results["errors"] == 0 else "failed",
        }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2))

    # Print summary to CI log
    icon = "✅" if summary["status"] == "passed" else "❌"
    print(f"\n{icon} {args.brand.upper()} Smoke Results:")
    print(f"   Total: {summary['total']}  |  Passed: {summary['passed']}  |  Failed: {summary['failed']}  |  Duration: {summary['duration_s']:.1f}s")

    for t in summary.get("tests", []):
        status_icon = {"passed": "✅", "failed": "❌", "error": "💥", "skipped": "⏭️"}.get(t["status"], "❓")
        print(f"   {status_icon} {t['name']} ({t['duration_s']:.1f}s)")
        if t.get("message"):
            print(f"      └─ {t['message'][:120]}")


if __name__ == "__main__":
    main()
