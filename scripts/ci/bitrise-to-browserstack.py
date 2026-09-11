#!/usr/bin/env python3
"""
Bitrise → BrowserStack App Transfer

Fetches the latest app build from Bitrise CI and uploads it directly
to BrowserStack Maestro with the brand's custom_id.

Eliminates the manual download-and-upload step:
  Before:  Bitrise UI → download APK → place in apps/ → run upload script
  Now:     python bitrise-to-browserstack.py --brand b3 --platform android

5-step flow (same as mobileAPPAutomation/src/ci/bitrise.ts):
  Step 1: Resolve Bitrise app slug + workflow from brand/env
  Step 2: GET /builds → latest successful build for the workflow
  Step 3: Extract build number + app version from tag
  Step 4: GET /builds/:slug/artifacts → find APK/IPA artifact
  Step 5: GET /artifacts/:slug → expiring download URL
  Step 6: Stream-download the binary
  Step 7: Upload to BrowserStack Maestro API with custom_id

Usage:
  python scripts/ci/bitrise-to-browserstack.py --brand b3 --platform android
  python scripts/ci/bitrise-to-browserstack.py --brand b3 --platform ios
  python scripts/ci/bitrise-to-browserstack.py --brand b1 --platform android --env demo
  python scripts/ci/bitrise-to-browserstack.py --brand b3 --info-only
  python scripts/ci/bitrise-to-browserstack.py --all --platform android          # all brands at once
  python scripts/ci/bitrise-to-browserstack.py --all --info-only                 # check all builds
  python scripts/ci/bitrise-to-browserstack.py --project menu-analysis --list    # different project
  python scripts/ci/bitrise-to-browserstack.py --list

Environment:
  BITRISE_AUTH_TOKEN     — Bitrise Personal Access Token
  BROWSERSTACK_USERNAME  — BrowserStack username
  BROWSERSTACK_ACCESS_KEY — BrowserStack access key
"""

import argparse
import json
import os
import re
import sys
import tempfile

# Fix Windows console encoding for emoji output
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith('cp'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)

# Auto-load .env file for local development (secrets never committed)
try:
    from dotenv import load_dotenv
    # Walk up from scripts/ci/ to find repo root .env
    _env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)
        print(f"[dotenv] Loaded .env from {os.path.abspath(_env_path)}")
except ImportError:
    pass  # python-dotenv not installed — rely on env vars directly


# ═══════════════════════════════════════════════════════════════════
#  Configuration — loaded from config/projects.yaml
# ═══════════════════════════════════════════════════════════════════

BITRISE_API_BASE = "https://api.bitrise.io/v0.1"
BS_MAESTRO_BASE = "https://api-cloud.browserstack.com/app-automate/maestro/v2"

# Default project — used when --project is not specified
DEFAULT_PROJECT = "maestro"

try:
    from shuriken_config import get_bitrise_apps, get_bs_custom_ids, get_project_names, get_project
    _USE_CONFIG = True
except ImportError:
    _USE_CONFIG = False

def _load_bitrise_apps(project_key: str) -> dict:
    """Load Bitrise app config from projects.yaml or fall back to hardcoded."""
    if _USE_CONFIG:
        return get_bitrise_apps(project_key)
    # Fallback — hardcoded (kept for standalone usage without pyyaml)
    return {
        "b3": {"title": "App-Brand3", "slug": "00000000-0000-0000-0000-000000000003", "abbreviation": "b3"},
        "b1": {"title": "WL-Brand One", "slug": "00000000-0000-0000-0000-000000000001", "abbreviation": "b1"},
        "b2": {"title": "WL-B2", "slug": "00000000-0000-0000-0000-000000000002", "abbreviation": "b2"},
        "b4": {"title": "WL-Brand Four", "slug": "00000000-0000-0000-0000-000000000004", "abbreviation": "b4"},
    }

def _load_bs_custom_ids(project_key: str) -> dict:
    """Load BrowserStack custom IDs from projects.yaml or fall back to hardcoded."""
    if _USE_CONFIG:
        return get_bs_custom_ids(project_key)
    return {
        "b3": {"android": "b3-staging", "ios": "b3-staging-ios"},
        "b1": {"android": "b1-staging", "ios": "b1-staging-ios"},
        "b2": {"android": "b2-staging", "ios": "b2-staging-ios"},
        "b4": {"android": "b4-staging", "ios": "b4-staging-ios"},
    }

# Initialize with default project (overridden by --project flag in main())
BITRISE_APPS = _load_bitrise_apps(DEFAULT_PROJECT)
BS_CUSTOM_IDS = _load_bs_custom_ids(DEFAULT_PROJECT)


# ═══════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════

def get_bitrise_token() -> str:
    token = os.environ.get("BITRISE_AUTH_TOKEN", "")
    if not token:
        print("❌ BITRISE_AUTH_TOKEN not set.")
        print("   Get your token: https://app.bitrise.io/me/profile#/security")
        sys.exit(1)
    return token


def get_bs_auth() -> tuple:
    username = os.environ.get("BROWSERSTACK_USERNAME", "")
    key = os.environ.get("BROWSERSTACK_ACCESS_KEY", "")
    if not username or not key:
        print("❌ BrowserStack credentials not set.")
        print("   Set BROWSERSTACK_USERNAME and BROWSERSTACK_ACCESS_KEY")
        sys.exit(1)
    return (username, key)


def bitrise_get(endpoint: str, token: str) -> dict:
    url = f"{BITRISE_API_BASE}{endpoint}"
    resp = requests.get(url, headers={
        "accept": "application/json",
        "Authorization": token,
    }, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Bitrise API {resp.status_code}: {url}")
        print(f"   {resp.text[:500]}")
        sys.exit(1)
    return resp.json()


def parse_version_from_tag(tag: str) -> str:
    """Extract version from Bitrise build tag.

    Tags follow: <abbreviation>/rc/<version>  e.g. 'b3/rc/8.3.4'
    """
    if not tag:
        return "—"
    match = re.search(r"/(?:rc|release)/(.+)$", tag, re.IGNORECASE)
    if match:
        return match.group(1)
    segments = tag.split("/")
    last = segments[-1]
    if re.match(r"^\d+\.\d+", last):
        return last
    return tag


def resolve_workflow(brand: str, env: str) -> str:
    """Resolve Bitrise workflow name.

    All brands now use the same workflow name matching the environment
    (e.g. 'uat', 'qa', 'demo'). Previously was '<abbreviation>-<env>-engine'.
    """
    app = BITRISE_APPS.get(brand)
    if not app:
        print(f"❌ Unknown brand '{brand}'. Valid: {', '.join(BITRISE_APPS.keys())}")
        sys.exit(1)
    return env


# ═══════════════════════════════════════════════════════════════════
#  Step 2: Get Latest Successful Build
# ═══════════════════════════════════════════════════════════════════

def get_latest_build(app_slug: str, workflow: str, token: str) -> dict:
    endpoint = f"/apps/{app_slug}/builds?workflow={workflow}&trigger_event_type=tag&status=1&limit=1"
    data = bitrise_get(endpoint, token)
    builds = data.get("data", [])
    if not builds:
        total = data.get("paging", {}).get("total_item_count", 0)
        print(f"❌ No successful builds found for workflow '{workflow}'")
        print(f"   Total builds matching filters: {total}")
        sys.exit(1)
    return builds[0]


# ═══════════════════════════════════════════════════════════════════
#  Step 4: Find Artifact (APK or IPA)
# ═══════════════════════════════════════════════════════════════════

def find_artifact(app_slug: str, build_slug: str, platform: str, token: str) -> dict:
    endpoint = f"/apps/{app_slug}/builds/{build_slug}/artifacts?limit=25"
    data = bitrise_get(endpoint, token)
    artifacts = data.get("data", [])

    if not artifacts:
        print(f"❌ No artifacts found for build {build_slug}")
        sys.exit(1)

    artifact = None
    if platform == "ios":
        # Prefer ios-ipa type, fallback to any .ipa
        artifact = next((a for a in artifacts if a.get("artifact_type") == "ios-ipa"), None)
        if not artifact:
            artifact = next((a for a in artifacts if a["title"].endswith(".ipa")), None)
    else:
        # Android: prefer FINAL-SIGNED .apk, fallback to any .apk
        artifact = next(
            (a for a in artifacts if "FINAL-SIGNED" in a["title"] and a["title"].endswith(".apk")),
            None,
        )
        if not artifact:
            artifact = next(
                (a for a in artifacts if a["title"].endswith(".apk") and not a["title"].endswith(".idsig")),
                None,
            )
        if not artifact:
            artifact = next((a for a in artifacts if a["title"].endswith(".apk")), None)

    if not artifact:
        available = "\n".join(f"  {a['title']} ({a.get('artifact_type', '?')})" for a in artifacts)
        ext = "IPA" if platform == "ios" else "APK"
        print(f"❌ No {ext} artifact found. Available artifacts:\n{available}")
        sys.exit(1)

    return artifact


# ═══════════════════════════════════════════════════════════════════
#  Step 5: Get Download URL
# ═══════════════════════════════════════════════════════════════════

def get_download_url(app_slug: str, build_slug: str, artifact_slug: str, token: str) -> dict:
    endpoint = f"/apps/{app_slug}/builds/{build_slug}/artifacts/{artifact_slug}"
    data = bitrise_get(endpoint, token)
    return data.get("data", {})


# ═══════════════════════════════════════════════════════════════════
#  Step 6: Download Binary
# ═══════════════════════════════════════════════════════════════════

def download_binary(url: str, local_path: str) -> int:
    """Stream-download a binary file. Returns file size in bytes."""
    print(f"⬇️  Downloading → {local_path}")
    resp = requests.get(url, stream=True, timeout=600)
    resp.raise_for_status()

    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    total = 0
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)

    size_mb = total / 1024 / 1024
    print(f"   ✅ Downloaded {size_mb:.1f} MB")
    return total


# ═══════════════════════════════════════════════════════════════════
#  Step 7: Upload to BrowserStack Maestro
# ═══════════════════════════════════════════════════════════════════

def upload_to_browserstack(file_path: str, custom_id: str) -> dict:
    """Upload APK/IPA to BrowserStack Maestro API. Returns API response."""
    auth = get_bs_auth()
    url = f"{BS_MAESTRO_BASE}/app"

    print(f"\n☁️  Uploading to BrowserStack...")
    print(f"   Custom ID: {custom_id}")
    print(f"   File: {file_path}")

    with open(file_path, "rb") as f:
        resp = requests.post(
            url,
            auth=auth,
            files={"file": (os.path.basename(file_path), f, "application/octet-stream")},
            data={"custom_id": custom_id},
            timeout=600,
        )

    if resp.status_code != 200:
        print(f"❌ BrowserStack upload failed: {resp.status_code} — {resp.text}")
        sys.exit(1)

    result = resp.json()
    print(f"   ✅ Uploaded: {result.get('app_url', '')}")
    print(f"   App Version: {result.get('app_version', '—')}")
    print(f"   Custom ID: {result.get('custom_id', custom_id)}")
    return result


# ═══════════════════════════════════════════════════════════════════
#  Main: Full Pipeline
# ═══════════════════════════════════════════════════════════════════

def fetch_latest_build(brand: str, env: str, platform: str, token: str) -> dict:
    """Full 5-step flow: resolve → build → artifact → download URL."""
    app = BITRISE_APPS[brand]
    workflow = resolve_workflow(brand, env)

    print(f"\n{'═' * 60}")
    print(f"  🚀 Bitrise → BrowserStack Transfer")
    print(f"  Brand: {app['title']}  |  Env: {env.upper()}  |  Platform: {platform.upper()}")
    print(f"  Workflow: {workflow}")
    print(f"{'═' * 60}")

    # Step 2: Latest build
    print(f"\n📦 Step 2/5 — Fetching latest build...")
    build = get_latest_build(app["slug"], workflow, token)
    version = parse_version_from_tag(build.get("tag", ""))
    build_num = build["build_number"]
    print(f"   ✅ Build #{build_num}  |  Tag: {build.get('tag', '—')}  |  Version: {version}")
    print(f"   Finished: {build.get('finished_at', '—')}")

    # Step 4: Find artifact
    print(f"\n🔎 Step 4/5 — Finding {platform.upper()} artifact...")
    artifact = find_artifact(app["slug"], build["slug"], platform, token)
    size_mb = artifact.get("file_size_bytes", 0) / 1024 / 1024
    print(f"   ✅ Found: {artifact['title']} ({artifact.get('artifact_type', '?')}, {size_mb:.1f} MB)")

    # Step 5: Download URL
    print(f"\n🔗 Step 5/5 — Getting download URL...")
    detail = get_download_url(app["slug"], build["slug"], artifact["slug"], token)
    download_url = detail.get("expiring_download_url", "")
    if not download_url:
        print("❌ No download URL returned by Bitrise API")
        sys.exit(1)
    print(f"   ✅ Download URL acquired (expires in ~10 min)")

    version_label = f"{version} (build {build_num})" if version != "—" else f"build {build_num}"

    return {
        "app_slug": app["slug"],
        "build_slug": build["slug"],
        "build_number": build_num,
        "app_version": version,
        "tag": build.get("tag", ""),
        "workflow": workflow,
        "finished_at": build.get("finished_at", ""),
        "artifact_title": artifact["title"],
        "artifact_type": artifact.get("artifact_type", ""),
        "file_size_bytes": artifact.get("file_size_bytes", 0),
        "download_url": download_url,
        "version_label": version_label,
    }


def main():
    global BITRISE_APPS, BS_CUSTOM_IDS

    # Build project choices dynamically
    project_choices = get_project_names() if _USE_CONFIG else [DEFAULT_PROJECT]

    parser = argparse.ArgumentParser(
        description="Fetch app from Bitrise → Upload to BrowserStack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", choices=project_choices, default=DEFAULT_PROJECT,
                        help=f"Project key (default: {DEFAULT_PROJECT}). See config/projects.yaml")
    parser.add_argument("--brand",
                        help="Brand code (b3, b1, b2, b4)")
    parser.add_argument("--all", action="store_true", dest="all_brands",
                        help="Process ALL brands for the selected project in one run")
    parser.add_argument("--platform", choices=["android", "ios"], default="android",
                        help="Target platform (default: android)")
    parser.add_argument("--env", choices=["qa", "uat", "demo", "stg"], default="uat",
                        help="Bitrise environment (default: uat)")
    parser.add_argument("--info-only", action="store_true",
                        help="Show build info without downloading or uploading")
    parser.add_argument("--download-only", action="store_true",
                        help="Download from Bitrise but don't upload to BrowserStack")
    parser.add_argument("--list", action="store_true", dest="list_targets",
                        help="List all available brand/env combinations")
    parser.add_argument("--token", default="",
                        help="Bitrise PAT override (default: BITRISE_AUTH_TOKEN env var)")

    args = parser.parse_args()

    # ── Reload config for selected project ──
    if args.project != DEFAULT_PROJECT:
        BITRISE_APPS = _load_bitrise_apps(args.project)
        BS_CUSTOM_IDS = _load_bs_custom_ids(args.project)

    # Validate --brand against current project's brands
    if args.brand and args.brand not in BITRISE_APPS:
        parser.error(f"Brand '{args.brand}' not found in project '{args.project}'. "
                     f"Available: {', '.join(BITRISE_APPS.keys())}")

    # ── --list: show all targets ──
    if args.list_targets:
        print(f"\n📋 Available targets for project '{args.project}':\n")
        for brand, app in BITRISE_APPS.items():
            for env in ["qa", "uat", "demo", "stg"]:
                wf = env  # All brands now use env name as workflow
                bs_ids = BS_CUSTOM_IDS.get(brand, {})
                bs_a = bs_ids.get("android", "—")
                bs_i = bs_ids.get("ios", "—")
                print(f"   {brand}-{env}  →  workflow: {wf}  |  BS: {bs_a} / {bs_i}")
        if _USE_CONFIG:
            print(f"\n   Available projects: {', '.join(project_choices)}")
            print(f"   Use --project <name> to switch project context")
        print()
        return

    if not args.brand and not args.all_brands:
        parser.error("--brand or --all is required (use --list to see options)")

    token = args.token or get_bitrise_token()
    platform = args.platform
    env = args.env

    # ── Determine brand list ──
    brands_to_process = list(BITRISE_APPS.keys()) if args.all_brands else [args.brand]

    if args.all_brands:
        print(f"\n{'═' * 60}")
        print(f"  🚀 BATCH MODE — All {len(brands_to_process)} brands")
        print(f"  Platform: {platform.upper()}  |  Env: {env.upper()}")
        print(f"  Brands: {', '.join(brands_to_process)}")
        print(f"{'═' * 60}")

    results_summary = []

    for brand in brands_to_process:
        try:
            # ── Fetch build info ──
            build_info = fetch_latest_build(brand, env, platform, token)

            if args.info_only:
                print(f"\n📋 Build Info Summary ({brand.upper()}):")
                print(f"   App Version:  {build_info['app_version']}")
                print(f"   Build Number: {build_info['build_number']}")
                print(f"   Tag:          {build_info['tag']}")
                print(f"   Workflow:     {build_info['workflow']}")
                print(f"   Artifact:     {build_info['artifact_title']}")
                print(f"   Size:         {build_info['file_size_bytes'] / 1024 / 1024:.1f} MB")
                print(f"   Built:        {build_info['finished_at']}")
                print(f"   Version:      {build_info['version_label']}")
                results_summary.append({"brand": brand, "status": "✅ info", "version": build_info['version_label']})
                continue

            # ── Step 6: Download ──
            ext = "ipa" if platform == "ios" else "apk"
            local_filename = f"{brand}-{env}.{ext}"
            local_path = os.path.join("apps", local_filename)

            print(f"\n⬇️  Step 6 — Downloading {build_info['artifact_title']}...")
            download_binary(build_info["download_url"], local_path)

            # Write build metadata sidecar
            meta_path = os.path.join("apps", f"{brand}-{env}-build-info.json")
            with open(meta_path, "w") as f:
                json.dump({
                    "brand": brand,
                    "env": env,
                    "platform": platform,
                    "app_version": build_info["app_version"],
                    "build_number": build_info["build_number"],
                    "tag": build_info["tag"],
                    "workflow": build_info["workflow"],
                    "artifact_title": build_info["artifact_title"],
                    "finished_at": build_info["finished_at"],
                    "downloaded_at": __import__("datetime").datetime.now().isoformat(),
                    "local_path": local_path,
                }, f, indent=2)
            print(f"   📋 Metadata → {meta_path}")

            if args.download_only:
                results_summary.append({"brand": brand, "status": "✅ downloaded", "version": build_info['version_label'], "file": local_path})
                continue

            # ── Step 7: Upload to BrowserStack ──
            custom_id = BS_CUSTOM_IDS[brand][platform]
            result = upload_to_browserstack(local_path, custom_id)

            results_summary.append({
                "brand": brand,
                "status": "✅ uploaded",
                "version": build_info['version_label'],
                "file": local_path,
                "bs_url": result.get('app_url', '—'),
                "custom_id": custom_id,
            })

        except SystemExit:
            # bitrise_get / find_artifact call sys.exit on failure — catch and continue in batch mode
            if args.all_brands:
                print(f"\n⚠️  Skipping {brand} due to error above — continuing with next brand...")
                results_summary.append({"brand": brand, "status": "❌ failed"})
                continue
            raise
        except Exception as e:
            if args.all_brands:
                print(f"\n⚠️  {brand} failed: {e} — continuing with next brand...")
                results_summary.append({"brand": brand, "status": f"❌ {e}"})
                continue
            raise

    # ── Final Summary ──
    print(f"\n{'═' * 60}")
    if args.all_brands:
        print(f"  📋 BATCH RESULTS — {len(results_summary)} brands processed")
        print(f"{'═' * 60}")
        for r in results_summary:
            version = r.get('version', '—')
            bs_url = r.get('bs_url', '')
            custom_id = r.get('custom_id', '')
            line = f"  {r['status']}  {r['brand'].upper():4s}  {version}"
            if custom_id:
                line += f"  →  {custom_id}"
            print(line)
    else:
        r = results_summary[0] if results_summary else {}
        if r.get('bs_url'):
            print(f"  ✅ Bitrise → BrowserStack Transfer Complete!")
            print(f"  Brand:      {BITRISE_APPS[brands_to_process[0]]['title']} ({brands_to_process[0]})")
            print(f"  Platform:   {platform.upper()}")
            print(f"  Version:    {r.get('version', '—')}")
            print(f"  Local File: {r.get('file', '—')}")
            print(f"  BS App URL: {r.get('bs_url', '—')}")
            print(f"  Custom ID:  {r.get('custom_id', '—')}")
        elif r.get('file'):
            print(f"  ✅ Download Complete (--download-only)")
            print(f"  Version: {r.get('version', '—')}")
            print(f"  File:    {r.get('file', '—')}")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    main()
