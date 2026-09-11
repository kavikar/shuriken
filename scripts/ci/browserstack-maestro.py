#!/usr/bin/env python3
"""
Shuriken — Run Maestro tests on BrowserStack real devices.

BrowserStack Maestro API v2 workflow:
  1. Upload app  → POST /maestro/v2/app       → app_url  (or reuse via custom_id)
  2. Upload flows (zip) → POST /maestro/v2/test-suite → test_suite_url
  3. Start build → POST /maestro/v2/{android|ios}/build → build_id
  4. Poll status → GET  /maestro/v2/builds/{build_id}   → results

Reference: https://www.browserstack.com/guide/run-maestro-tests-on-browserstack

Brands:  b3 (Brand Three)  |  b1 (Brand One)  |  b2 (Brand Two)  |  b4 (Brand Four)

Usage:
  . .\\scripts\\load-env.ps1
  # Android (default)
  python scripts/ci/browserstack-maestro.py --brand b3 --flow projects/automation/maestro/flows/brand3/auth/sign-in-out.yaml
  python scripts/ci/browserstack-maestro.py --brand b3 --suite smoke
  # iOS
  python scripts/ci/browserstack-maestro.py --brand b3 --platform ios --suite order --devices "iPhone 16 Pro Max-18"
  # Brand Four
  python scripts/ci/browserstack-maestro.py --brand b4 --suite smoke
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)

# Force UTF-8 on CI runners (Docker / GitLab)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str, level: str = "INFO"):
    """Timestamped log line for pipeline visibility."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

# ── Config ────────────────────────────────────────────────────────
BS_BASE = "https://api-cloud.browserstack.com/app-automate/maestro/v2"

# ── Brand Registry ───────────────────────────────────────────────
# 3-letter brand code → full config.  Single source of truth.
# Credentials are read from environment variables (GitLab CI/CD Variables
# or local .env / load-env.ps1). Never hardcode secrets here.
BRANDS = {
    "b3": {
        "name": "Brand Three",
        "flow_dir": "brand3",          # projects/automation/maestro/flows/brand3/...
        "bundle_id": "com.example.brand3.uat",
        "app_android": "apps/b3-uat.apk",
        "app_ios": "apps/b3-uat.ipa",
        "custom_id_android": "b3-staging",
        "custom_id_ios": "b3-staging-ios",
        "geo_location": "33.8889,-84.3185",  # near zip 00000 (Example City/Sandy Springs)
        "env": {
            "AUTH_EMAIL": "user@example.com",
            "AUTH_PASS":  "replace_me",
            "AUTH_PHONE": "5555550100",
            "OTP_BRAND_CODE": "B3",
            "OTP_API_PREFIX": "b3-api",
        },
    },
    "b1": {
        "name": "Brand One",
        "flow_dir": "Brand One",          # projects/automation/maestro/flows/brand1/...
        "bundle_id": "com.example.brand1.uat",
        "app_android": "apps/b1-uat.apk",
        "app_ios": "apps/b1-uat.ipa",
        "custom_id_android": "b1-staging",
        "custom_id_ios": "b1-staging-ios",
        "geo_location": "33.7490,-84.3880",  # Example City, GA
        "env": {
            "AUTH_EMAIL": "user@example.com",
            "AUTH_PASS":  "replace_me",
            "AUTH_PHONE": "5555550100",
            "OTP_BRAND_CODE": "B1",
            "OTP_API_PREFIX": "b1-api",
        },
    },
    "b2": {
        "name": "B2",
        "flow_dir": "b2",            # projects/automation/maestro/flows/b2/...
        "bundle_id": "com.example.brand2.uat",
        "app_android": "apps/b2-uat.apk",
        "app_ios": "apps/b2-uat.ipa",
        "custom_id_android": "b2-staging",
        "custom_id_ios": "b2-staging-ios",
        "geo_location": "33.7490,-84.3880",  # Example City, GA
        "env": {
            "AUTH_EMAIL": "user@example.com",
            "AUTH_PASS":  "replace_me",
            "AUTH_PHONE": "5555550100",
            "OTP_BRAND_CODE": "B2",
            "OTP_API_PREFIX": "b2-api",
        },
    },
    "b4": {
        "name": "Brand Four",
        "flow_dir": "Brand Four",         # projects/automation/maestro/flows/brand4/...
        "bundle_id": "com.example.brand4.uat.uat",
        "app_android": "apps/b4-uat.apk",
        "app_ios": "apps/b4-uat.ipa",
        "custom_id_android": "b4-staging",
        "custom_id_ios": "b4-staging-ios",
        "geo_location": "33.7490,-84.3880",  # Example City, GA
        "env": {
            "AUTH_EMAIL": "user@example.com",
            "AUTH_PASS":  "replace_me",
            "AUTH_PHONE": "5555550100",
            "OTP_BRAND_CODE": "B4",
            "OTP_API_PREFIX": "b4-api",
        },
    },
}

BRAND_CODES = list(BRANDS.keys())  # ["b3", "b1", "b2", "b4"]

# Default devices per platform
DEFAULT_DEVICES_ANDROID = ["Samsung Galaxy S25 Ultra-15.0", "Google Pixel 10 Pro XL-16.0"]
DEFAULT_DEVICES_IOS = ["iPhone 16 Pro Max-18"]


def get_auth():
    username = os.environ.get("BROWSERSTACK_USERNAME", "")
    access_key = os.environ.get("BROWSERSTACK_ACCESS_KEY", "")
    if not username or not access_key:
        log("BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY must be set", "ERROR")
        sys.exit(1)
    log(f"Auth: user={username}, key={'*' * (len(access_key) - 4) + access_key[-4:] if len(access_key) > 4 else '***'}")
    return (username, access_key)


# ── Step 1: Upload App ───────────────────────────────────────────

def get_app_version(app_url: str = "", custom_id: str = "") -> str:
    """Query BrowserStack for the app version of an already-uploaded app."""
    auth = get_auth()
    app_hash = app_url.replace("bs://", "") if app_url.startswith("bs://") else ""
    log(f"Fetching app version (app_url={app_url}, custom_id={custom_id})")
    
    try:
        url = f"{BS_BASE}/apps"
        resp = requests.get(url, auth=auth, timeout=30)
        log(f"GET {url} → {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            apps = data.get("apps", data) if isinstance(data, dict) else data
            if isinstance(apps, list):
                for app in apps:
                    # Match by custom_id first (most reliable), then app_url/app_id
                    if ((custom_id and app.get("custom_id") == custom_id) or
                        (app_url and app.get("app_url") == app_url) or
                        (app_hash and app.get("app_id") == app_hash)):
                        version = app.get("app_version", "")
                        if version:
                            log(f"Found app version: {version}")
                            return version
    except Exception as e:
        log(f"Could not fetch app version: {e}", "WARN")
    
    return ""


def get_app_url_by_custom_id(custom_id: str) -> str:
    """Look up the bs:// app_url for a previously uploaded app by its custom_id."""
    auth = get_auth()
    log(f"Looking up app by custom_id: {custom_id}")
    try:
        url = f"{BS_BASE}/apps"
        resp = requests.get(url, auth=auth, timeout=30)
        log(f"GET {url} → {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            apps = data.get("apps", data) if isinstance(data, dict) else data
            if isinstance(apps, list):
                for app in apps:
                    if app.get("custom_id") == custom_id:
                        app_url = app.get("app_url", "")
                        if app_url:
                            log(f"Found app by custom_id '{custom_id}': {app_url}")
                            return app_url
    except Exception as e:
        log(f"Could not look up app by custom_id: {e}", "WARN")
    return ""


def upload_app(apk_path: str, custom_id: str) -> tuple:
    """Upload APK/IPA to BrowserStack Maestro API. Returns (app_url, app_version)."""
    auth = get_auth()
    url = f"{BS_BASE}/app"

    file_size_mb = os.path.getsize(apk_path) / (1024 * 1024)
    log(f"─── STEP 1: Upload App ───")
    log(f"App path: {apk_path}")
    log(f"App size: {file_size_mb:.2f} MB")
    log(f"Custom ID: {custom_id}")
    log(f"POST → {url}")

    with open(apk_path, "rb") as f:
        resp = requests.post(
            url,
            auth=auth,
            files={"file": (os.path.basename(apk_path), f, "application/octet-stream")},
            data={"custom_id": custom_id},
            timeout=600,  # 10 min for large APKs
        )

    log(f"Response: {resp.status_code}")
    if resp.status_code != 200:
        log(f"Upload failed: {resp.status_code} — {resp.text}", "ERROR")
        sys.exit(1)

    result = resp.json()
    log(f"Response body: {json.dumps(result, indent=2)}")
    app_url = result.get("app_url", "")
    app_version = result.get("app_version", result.get("appVersion", ""))
    log(f"✅ App uploaded: {app_url}")
    if app_version:
        log(f"App version: {app_version}")
    return app_url, app_version


# ── Step 2: Upload Test Suite ────────────────────────────────────

def create_test_suite_zip(flows: list, shared_dir: str = "projects/automation/maestro/shared") -> str:
    """Create a zip of specific flow files + shared sub-flows for BrowserStack.
    
    Only includes the exact files requested in `flows` list (not entire directories).
    Always includes all shared/ sub-flows since they may be referenced.
    
    BrowserStack REQUIRES the zip to have a single parent folder at the root.
    Ref: https://www.browserstack.com/docs/app-automate/maestro/get-started/structure-your-tests
    
    Zip structure (PARENT_FOLDER wraps everything):
        shuriken/
        ├── flows/brand3/smoke/app-launch.yaml
        ├── flows/brand3/smoke/browse-menu.yaml
        └── shared/launch-and-dismiss.yaml
    
    Execute paths are relative to the parent folder:
        "execute": ["flows/brand3/smoke/app-launch.yaml"]
    
    Relative refs like ../../../shared/ from flows/brand/suite/ resolve to shared/
    within the parent folder.
    """
    # Maestro project root — file paths relative to this become zip entries
    MAESTRO_ROOT = "projects/automation/maestro"
    # BrowserStack requires a single parent folder at zip root
    PARENT_FOLDER = "shuriken"

    log(f"─── STEP 2a: Create Test Suite ZIP ───")
    log(f"MAESTRO_ROOT = {MAESTRO_ROOT}")
    log(f"PARENT_FOLDER = {PARENT_FOLDER}")
    log(f"shared_dir = {shared_dir} (exists: {os.path.isdir(shared_dir)})")
    log(f"Number of flow files: {len(flows)}")
    for i, fl in enumerate(flows):
        log(f"  flow[{i}]: {fl} (exists: {Path(fl).is_file()})")

    tmp_dir = tempfile.mkdtemp(prefix="shuriken-suite-")
    zip_path = os.path.join(tmp_dir, "shuriken-suite.zip")
    log(f"Zip path: {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add shared sub-flows (YAML + JS scripts)
        shared_count = 0
        if os.path.isdir(shared_dir):
            for root, _dirs, files in os.walk(shared_dir):
                for file in files:
                    if not file.endswith((".yaml", ".yml", ".js")):
                        continue
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, MAESTRO_ROOT)
                    arc_name = f"{PARENT_FOLDER}/{rel_path}".replace("\\", "/")
                    zf.write(abs_path, arc_name)
                    shared_count += 1
            log(f"Added {shared_count} shared sub-flow/script files")
        else:
            log(f"⚠️  shared_dir not found: {shared_dir}", "WARN")

        # Add only the specified flow files
        flow_count = 0
        for flow in flows:
            flow_path = Path(flow)
            if flow_path.is_file():
                rel_path = os.path.relpath(str(flow_path), MAESTRO_ROOT)
                arc_name = f"{PARENT_FOLDER}/{rel_path}".replace("\\", "/")
                zf.write(str(flow_path), arc_name)
                flow_count += 1
                log(f"  + {arc_name}")
            else:
                log(f"  ⚠️  Flow file not found: {flow}", "WARN")

        log(f"Added {flow_count} flow files")

        # Print zip contents
        log(f"── Zip contents ({shared_count + flow_count} files) ──")
        for info in zf.infolist():
            log(f"  📄 {info.filename}  ({info.file_size} bytes)")

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    log(f"Suite zip created: {zip_path} ({size_mb:.2f} MB)")
    return zip_path


def upload_test_suite(zip_path: str, custom_id: str = "shuriken-suite") -> str:
    """Upload test suite zip to BrowserStack. Returns test_suite_url."""
    auth = get_auth()
    url = f"{BS_BASE}/test-suite"

    zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    log(f"─── STEP 2b: Upload Test Suite ───")
    log(f"Zip: {zip_path} ({zip_size_mb:.2f} MB)")
    log(f"Custom ID: {custom_id}")
    log(f"POST → {url}")

    with open(zip_path, "rb") as f:
        resp = requests.post(
            url,
            auth=auth,
            files={"file": (os.path.basename(zip_path), f, "application/zip")},
            data={"custom_id": custom_id},
            timeout=120,
        )

    log(f"Response: {resp.status_code}")
    if resp.status_code != 200:
        log(f"Suite upload failed: {resp.status_code} — {resp.text}", "ERROR")
        sys.exit(1)

    result = resp.json()
    log(f"Response body: {json.dumps(result, indent=2)}")
    suite_url = result.get("test_suite_url", "")
    log(f"✅ Suite uploaded: {suite_url}")
    return suite_url


# ── Step 3: Start Build ─────────────────────────────────────────

def start_build(
    app_url: str,
    test_suite_url: str,
    devices: list,
    platform: str = "android",
    project: str = "Shuriken",
    env_vars: dict = None,
    execute: list = None,
    use_local: bool = False,
    geo_location: str = "",
) -> str:
    """Start a Maestro test build on BrowserStack devices. Returns build_id.
    
    Uses /android/build or /ios/build endpoint depending on platform.
    Set use_local=True only when BrowserStack Local tunnel is running.
    geo_location: GPS coords as "lat,lng" (e.g. "33.749,-84.388") — sets
                  device GPS so the app's location APIs work on cloud devices.
    """
    auth = get_auth()
    url = f"{BS_BASE}/{platform}/build"

    log(f"─── STEP 3: Start Build ───")
    log(f"Platform: {platform}")
    log(f"POST → {url}")

    payload = {
        "app": app_url,
        "testSuite": test_suite_url,
        "project": project,
        "devices": devices,
        "deviceLogs": "true",
        "networkLogs": "true",
        "video": "true",
    }

    if use_local:
        payload["local"] = "true"

    if geo_location:
        payload["gpsLocation"] = geo_location

    if env_vars:
        payload["setEnvVariables"] = env_vars

    if execute:
        payload["execute"] = execute

    # Log the FULL payload so we can debug exactly what BrowserStack receives
    log(f"Request payload:")
    for k, v in payload.items():
        if k == "setEnvVariables":
            # Mask passwords in env vars
            masked = {ek: ("***" if "PASS" in ek.upper() or "KEY" in ek.upper() else ev) for ek, ev in v.items()}
            log(f"  {k}: {json.dumps(masked)}")
        else:
            log(f"  {k}: {json.dumps(v) if isinstance(v, (list, dict)) else v}")

    resp = requests.post(url, auth=auth, json=payload, timeout=60)

    log(f"Response: {resp.status_code}")
    log(f"Response body: {resp.text[:2000]}")

    if resp.status_code not in (200, 201):
        log(f"Build start failed: {resp.status_code} — {resp.text}", "ERROR")
        sys.exit(1)

    result = resp.json()
    build_id = result.get("build_id", "")
    log(f"✅ Build started: {build_id}")
    log(f"Dashboard: https://app-automate.browserstack.com/builds/{build_id}")
    return build_id


# ── Step 4: Poll Status ─────────────────────────────────────────

def poll_build(build_id: str, timeout_min: int = 15, interval_s: int = 30) -> dict:
    """Poll build status until complete or timeout."""
    auth = get_auth()
    url = f"{BS_BASE}/builds/{build_id}"

    log(f"─── STEP 4: Poll Build Status ───")
    log(f"Build ID: {build_id}")
    log(f"GET → {url}")
    log(f"Timeout: {timeout_min} min | Poll interval: {interval_s}s")

    start = time.time()
    max_seconds = timeout_min * 60
    poll_count = 0

    while time.time() - start < max_seconds:
        poll_count += 1
        try:
            resp = requests.get(url, auth=auth, timeout=30)
            elapsed = int(time.time() - start)
            if resp.status_code == 200:
                data = resp.json()
                status = data.get("status", "unknown")
                log(f"Poll #{poll_count} [{elapsed}s] — Status: {status}")

                if status in ("done", "passed", "failed", "error", "timed_out"):
                    data["_elapsed_s"] = round(time.time() - start, 1)
                    log(f"Build finished with status: {status} (elapsed: {data['_elapsed_s']}s)")
                    # Log raw result for debugging
                    log(f"Raw result keys: {list(data.keys())}")
                    if "devices" in data:
                        log(f"Devices in result: {len(data['devices'])}")
                        for i, dev in enumerate(data["devices"]):
                            dev_name = dev.get("device", dev.get("device_name", f"device-{i}"))
                            dev_tests = dev.get("tests", dev.get("test_results", []))
                            log(f"  Device[{i}]: {dev_name} — {len(dev_tests)} tests")
                            for t in dev_tests[:10]:  # first 10
                                t_name = t.get("test_name", t.get("name", "?"))
                                t_status = t.get("status", "?")
                                log(f"    • {t_name}: {t_status}")
                    return data
            else:
                log(f"Poll #{poll_count} [{elapsed}s] — HTTP {resp.status_code}: {resp.text[:500]}", "WARN")
        except Exception as e:
            log(f"Poll #{poll_count} error: {e}", "WARN")

        time.sleep(interval_s)

    log(f"⚠️  Timeout after {timeout_min} minutes ({poll_count} polls)", "WARN")
    return {"status": "timeout", "build_id": build_id, "_elapsed_s": round(time.time() - start, 1)}


# ── Generate Summary for Confluence/Notify ───────────────────────

def generate_summary(brand: str, build_id: str, result: dict, flows: list, app_version: str = "") -> dict:
    """Parse BrowserStack poll result and produce a *-summary.json file
    that publish-confluence-report.py and notify.py can consume.

    Expected output format:
    {
      "brand": "brand3",
      "status": "passed" | "failed" | "error",
      "total": N,
      "passed": N,
      "failed": N,
      "errors": N,
      "skipped": 0,
      "duration_s": float,
      "app_version": "x.y.z",
      "tests": [ { "name": "...", "status": "...", "duration_s": ..., "message": "..." } ]
    }
    """
    bs_status = result.get("status", "unknown")
    # Wall-clock elapsed time injected by poll_build()
    wall_clock_s = result.get("_elapsed_s", 0.0)
    tests = []
    total_duration = 0.0

    log(f"── Generate Summary ──")
    log(f"BrowserStack status: {bs_status}")
    log(f"Wall clock: {wall_clock_s}s")

    # BrowserStack Maestro v2 result structure may vary;
    # parse test-level details from 'tests' or 'devices' arrays.
    device_results = result.get("devices", [])
    if not device_results:
        # Try alternate key names from BrowserStack API
        device_results = result.get("test_results", [])

    log(f"Device results: {len(device_results)} device(s)")

    for device in device_results:
        device_tests = device.get("tests", device.get("test_results", []))
        if isinstance(device_tests, list):
            for t in device_tests:
                t_name = t.get("test_name", t.get("name", t.get("file_name", "unknown")))
                t_status_raw = t.get("status", "unknown").lower()
                t_duration = float(t.get("duration", t.get("duration_ms", 0)))
                # BrowserStack may return ms or seconds — normalise to seconds
                if t_duration > 1000:
                    t_duration = t_duration / 1000.0
                t_message = t.get("message", t.get("error", ""))
                t_status = "passed" if t_status_raw in ("passed", "pass", "done") else \
                           "failed" if t_status_raw in ("failed", "fail") else \
                           "error" if t_status_raw in ("error", "timed_out", "timeout") else t_status_raw
                tests.append({
                    "name": t_name,
                    "status": t_status,
                    "duration_s": round(t_duration, 1),
                    "message": str(t_message)[:500],
                })
                total_duration += t_duration

    # If BrowserStack didn't return test-level detail, synthesise from build status
    if not tests:
        # Count how many flows we submitted
        n_flows = max(len(flows), 1)
        if bs_status in ("done", "passed"):
            tests = [{"name": f.replace("\\", "/").split("/")[-1], "status": "passed",
                       "duration_s": 0, "message": ""} for f in flows] or \
                    [{"name": "build", "status": "passed", "duration_s": 0, "message": ""}]
        else:
            tests = [{"name": f.replace("\\", "/").split("/")[-1], "status": "failed",
                       "duration_s": 0, "message": f"Build status: {bs_status}"} for f in flows] or \
                    [{"name": "build", "status": "failed", "duration_s": 0, "message": f"Build status: {bs_status}"}]

    n_passed = sum(1 for t in tests if t["status"] == "passed")
    n_failed = sum(1 for t in tests if t["status"] == "failed")
    n_errors = sum(1 for t in tests if t["status"] == "error")
    overall = "passed" if n_failed == 0 and n_errors == 0 else "failed"

    # Use wall-clock elapsed time if BrowserStack didn't provide test-level durations
    if total_duration == 0.0 and wall_clock_s > 0:
        total_duration = wall_clock_s

    summary = {
        "brand": brand,
        "build_id": build_id,
        "status": overall,
        "total": len(tests),
        "passed": n_passed,
        "failed": n_failed,
        "errors": n_errors,
        "skipped": 0,
        "duration_s": round(total_duration, 1),
        "app_version": app_version,
        "tests": tests,
    }

    print(f"\n📊 Summary: {brand.upper()} — {overall.upper()}")
    print(f"   Total: {len(tests)} | Passed: {n_passed} | Failed: {n_failed} | Errors: {n_errors}")
    log(f"Summary: {brand.upper()} — {overall.upper()} | Total: {len(tests)} | Passed: {n_passed} | Failed: {n_failed} | Errors: {n_errors}")
    return summary


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Shuriken — Run Maestro on BrowserStack")
    parser.add_argument("--brand", required=True, choices=BRAND_CODES,
                        help="Brand code: b3 (Brand Three), b1 (Brand One), b2 (B2), b4 (Brand Four)")
    parser.add_argument("--platform", default="android", choices=["android", "ios"],
                        help="Target platform (default: android)")
    parser.add_argument("--flow", help="Specific flow YAML file to run")
    parser.add_argument("--suite", help="Suite folder (e.g., 'smoke', 'auth')")
    parser.add_argument("--devices", nargs="+", default=None,
                        help="BrowserStack device list (auto-detected per platform if omitted)")
    parser.add_argument("--async", dest="async_mode", action="store_true", help="Don't wait for results")
    parser.add_argument("--local", action="store_true",
                        help="Enable BrowserStack Local tunnel (requires BrowserStackLocal binary running)")
    parser.add_argument("--skip-upload-app", action="store_true",
                        help="Skip app upload — reuse last uploaded app via custom_id")
    parser.add_argument("--app-url", help="Use existing app_url (bs://...) instead of uploading")
    parser.add_argument("--suite-url", help="Use existing test_suite_url instead of uploading")
    parser.add_argument("--geo-location", default="",
                        help="GPS coords as 'lat,lng' to set on the BrowserStack device (e.g. '33.749,-84.388')")
    parser.add_argument("--output", default="test-results/browserstack-result.json")
    args = parser.parse_args()

    # ── Startup banner ──
    log("=" * 60)
    log("🍽️  Shuriken — BrowserStack Maestro Runner")
    log(f"Python: {sys.version}")
    log(f"CWD: {os.getcwd()}")
    log(f"Script: {os.path.abspath(__file__)}")
    log(f"Timestamp: {datetime.datetime.now().isoformat()}")
    log("=" * 60)

    brand = args.brand
    brand_cfg = BRANDS[brand]
    platform = args.platform
    bundle_id = brand_cfg["bundle_id"]
    flow_dir = brand_cfg["flow_dir"]
    custom_id = brand_cfg[f"custom_id_{platform}"]

    log(f"Brand: {brand_cfg['name']} ({brand})")
    log(f"Platform: {platform}")
    log(f"Bundle ID: {bundle_id}")
    log(f"Flow dir: {flow_dir}")
    log(f"Custom ID: {custom_id}")
    log(f"CLI args: flow={args.flow}, suite={args.suite}, devices={args.devices}")
    log(f"  skip_upload_app={args.skip_upload_app}, app_url={args.app_url}, suite_url={args.suite_url}")
    log(f"  async={args.async_mode}, local={args.local}, geo_location={args.geo_location}")

    # Resolve default devices per platform
    if args.devices:
        devices = args.devices
    else:
        devices = DEFAULT_DEVICES_IOS if platform == "ios" else DEFAULT_DEVICES_ANDROID

    # ── Path constants ──
    MAESTRO_ROOT = "projects/automation/maestro"
    FLOWS_BASE = f"{MAESTRO_ROOT}/flows"

    log(f"── Flow Resolution ──")
    log(f"MAESTRO_ROOT = {MAESTRO_ROOT} (exists: {os.path.isdir(MAESTRO_ROOT)})")
    log(f"FLOWS_BASE = {FLOWS_BASE} (exists: {os.path.isdir(FLOWS_BASE)})")

    # Determine which flows to include
    # NOTE: execute paths must be relative to the parent folder in the zip,
    #       e.g. "flows/brand3/smoke/app-launch.yaml"
    #       BrowserStack docs: "All paths in the execute array are relative to your parent folder."
    flows = []
    execute = []
    if args.flow:
        log(f"Mode: single flow — {args.flow}")
        flows = [args.flow]
        rel = args.flow.replace("\\", "/")
        if rel.startswith(f"{MAESTRO_ROOT}/"):
            rel = rel[len(f"{MAESTRO_ROOT}/"):]

        execute = [rel]
        log(f"Execute path: {rel}")
    elif args.suite:
        suite_path = f"{FLOWS_BASE}/{flow_dir}/{args.suite}"
        log(f"Mode: suite — looking for: {suite_path} (exists: {os.path.isdir(suite_path)})")
        if os.path.isdir(suite_path):
            for f in sorted(Path(suite_path).glob("*.yaml")):
                flows.append(str(f))
            for f in sorted(Path(suite_path).glob("*.yml")):
                flows.append(str(f))
        else:
            log(f"Suite dir not found directly, scanning {FLOWS_BASE}/{flow_dir}/ for fuzzy match...")
            for d in Path(f"{FLOWS_BASE}/{flow_dir}").iterdir():
                log(f"  Checking: {d.name} (is_dir={d.is_dir()})")
                if d.is_dir() and args.suite.lower() in d.name.lower():
                    log(f"  Matched: {d.name}")
                    for f in sorted(d.glob("*.yaml")):
                        flows.append(str(f))
                    for f in sorted(d.glob("*.yml")):
                        flows.append(str(f))
                    break
        if not flows:
            log(f"❌ Suite not found: {suite_path}", "ERROR")
            # List what exists for debugging
            if os.path.isdir(f"{FLOWS_BASE}/{flow_dir}"):
                contents = list(Path(f"{FLOWS_BASE}/{flow_dir}").iterdir())
                log(f"Available in {FLOWS_BASE}/{flow_dir}/: {[c.name for c in contents]}")
            sys.exit(1)
        for f in flows:
            rel = f.replace("\\", "/")
            if rel.startswith(f"{MAESTRO_ROOT}/"):
                rel = rel[len(f"{MAESTRO_ROOT}/"):]
            execute.append(rel)
    else:
        log(f"Mode: all flows in {FLOWS_BASE}/{flow_dir}/")
        for f in sorted(Path(f"{FLOWS_BASE}/{flow_dir}").rglob("*.yaml")):
            flows.append(str(f))

    log(f"Resolved {len(flows)} flow(s):")
    for i, fl in enumerate(flows):
        log(f"  [{i}] {fl}")
    log(f"Execute list ({len(execute)} entries):")
    for i, ex in enumerate(execute):
        log(f"  [{i}] {ex}")

    print("=" * 60)
    print(f"  🍽️  Shuriken — BrowserStack Maestro Runner")
    print(f"  Brand: {brand_cfg['name'].upper()} ({brand}) | Platform: {platform.upper()} | Bundle: {bundle_id}")
    print(f"  Custom ID: {custom_id}")
    print("=" * 60)

    # Step 1: Upload or reuse app
    app_version = ""
    if args.app_url:
        # Explicit bs:// URL provided
        app_url = args.app_url
        log(f"Step 1: Using existing app URL: {app_url}")
        app_version = get_app_version(app_url=app_url, custom_id=custom_id)
    elif args.skip_upload_app:
        # Reuse last uploaded app via custom_id lookup
        log(f"Step 1: Looking up app by custom_id: {custom_id}")
        app_url = get_app_url_by_custom_id(custom_id)
        if not app_url:
            log(f"❌ No app found for custom_id '{custom_id}'. Upload first or remove --skip-upload-app.", "ERROR")
            sys.exit(1)
        app_version = get_app_version(custom_id=custom_id)
    else:
        # Upload fresh
        app_key = f"app_{platform}"
        app_path = brand_cfg[app_key]
        log(f"Step 1: Uploading app — {app_path} (exists: {os.path.isfile(app_path)})")
        if not os.path.isfile(app_path):
            log(f"❌ App not found: {app_path}", "ERROR")
            sys.exit(1)
        app_url, app_version = upload_app(app_path, custom_id)

    log(f"Step 1 complete: app_url={app_url}, version={app_version}")

    # Step 2: Upload test suite
    if args.suite_url:
        suite_url = args.suite_url
        log(f"Step 2: Using existing suite: {suite_url}")
    else:
        log(f"Step 2: Packaging & uploading test suite...")
        zip_path = create_test_suite_zip(flows)
        suite_url = upload_test_suite(zip_path, f"{brand}-shuriken-suite")

    log(f"Step 2 complete: suite_url={suite_url}")

    # Step 3: Start build
    log(f"Step 3: Starting BrowserStack build...")
    env_vars = {"BUNDLE_ID": bundle_id, "PLATFORM": platform}
    env_vars.update(brand_cfg.get("env", {}))
    log(f"Env vars: {list(env_vars.keys())}")

    # Resolve GPS location: CLI arg > brand config > empty
    geo_location = args.geo_location or brand_cfg.get("geo_location", "")
    log(f"GPS location: {geo_location or '(none)'}")

    build_id = start_build(
        app_url=app_url,
        test_suite_url=suite_url,
        devices=devices,
        platform=platform,
        project=f"Shuriken-{brand.upper()}-{platform.upper()}",
        env_vars=env_vars,
        execute=execute if execute else None,
        use_local=args.local,
        geo_location=geo_location,
    )

    # Save build info
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    build_info = {
        "build_id": build_id,
        "brand": brand,
        "brand_name": brand_cfg["name"],
        "platform": platform,
        "app_url": app_url,
        "app_version": app_version,
        "custom_id": custom_id,
        "suite_url": suite_url,
        "devices": devices,
        "dashboard": f"https://app-automate.browserstack.com/builds/{build_id}",
    }
    Path(args.output).write_text(json.dumps(build_info, indent=2))
    log(f"Step 3 complete: build_id={build_id}")
    log(f"Build info saved: {args.output}")

    if args.async_mode:
        log(f"🔗 Build running async. Check dashboard:")
        log(f"https://app-automate.browserstack.com/builds/{build_id}")
        return

    # Step 4: Poll for results
    log(f"Step 4: Polling for results...")
    result = poll_build(build_id)

    # Update output
    build_info["result"] = result
    Path(args.output).write_text(json.dumps(build_info, indent=2))

    status = result.get("status", "unknown")
    log(f"─── RESULT ───")
    if status in ("done", "passed"):
        log(f"✅ Build PASSED!")
    else:
        log(f"❌ Build status: {status}")

    log(f"Dashboard: https://app-automate.browserstack.com/builds/{build_id}")
    log(f"Results saved: {args.output}")

    # ── Generate summary.json for downstream report/notify stages ──
    log(f"Generating summary...")
    summary = generate_summary(brand, build_id, result, flows, app_version=app_version)
    summary["platform"] = platform
    summary["brand_name"] = brand_cfg["name"]
    output_stem = Path(args.output).stem.replace("-result", "")
    summary_path = str(Path(args.output).parent / f"{output_stem}-summary.json")
    Path(summary_path).write_text(json.dumps(summary, indent=2))
    log(f"Summary saved: {summary_path}")
    log(f"── Shuriken run complete ──")


if __name__ == "__main__":
    main()
