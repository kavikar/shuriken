"""
Menu Delta Analyzer – Flask Web Application
Supports B1, B2, and B3 brands.
Compares PROD vs UAT menu endpoints and produces a multi-sheet Excel report.
"""

import json
import os
import sys
import uuid
import traceback
from pathlib import Path

from flask import Flask, jsonify, request, send_file, render_template, abort

# ── Path setup ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from core.fetcher import fetch_prod_and_uat
from core.parser import parse_menu
from core.comparator import compare
from core import report_generator

# ── Config ───────────────────────────────────────────────────────────────────
BRANDS_CFG_PATH = BASE_DIR / "config" / "brands.json"
REPORTS_DIR     = BASE_DIR / "reports"
HISTORY_FILE    = BASE_DIR / "reports" / "history.json"
MAX_HISTORY_PER_BRAND = 5

with open(BRANDS_CFG_PATH, "r", encoding="utf-8") as fh:
    BRANDS = json.load(fh)

def _reload_brands():
    """Re-read brands.json on every request so store_map changes take effect without restart."""
    global BRANDS
    with open(BRANDS_CFG_PATH, "r", encoding="utf-8") as fh:
        BRANDS = json.load(fh)

def _load_history() -> dict:
    """Load persisted brand-wise history from disk."""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}

def _save_history(h: dict):
    """Persist brand-wise history to disk."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as fh:
        json.dump(h, fh, indent=2)

# In-memory store: report_id -> { filepath, meta }
_report_store: dict = {}

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
app.json.sort_keys = False          # preserve Python dict insertion order in API responses
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB for uploads


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/brands", methods=["GET"])
def get_brands():
    return jsonify({
        brand: {
            "name": cfg["name"],
            "short": cfg["short"],
            "color": cfg["color"],
            "logo_char": cfg.get("logo_char", ""),
            "store_map": cfg.get("store_map", {}),
        }
        for brand, cfg in BRANDS.items()
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Expected JSON body:
    {
      "brand":        "B2",
      "prod_store_id":"1000",
      "uat_store_id": "1001",    // optional – auto-resolved from store_map
      "prod_json":    {...},     // optional – skip live fetch, use this
      "uat_json":     {...}      // optional – skip live fetch, use this
    }
    """
    _reload_brands()
    try:
        data = request.get_json(force=True) or {}

        brand_key  = (data.get("brand") or "").upper().strip()
        prod_store = str(data.get("prod_store_id") or "").strip()
        uat_store  = str(data.get("uat_store_id") or "").strip()
        prod_json  = data.get("prod_json")   # pre-loaded JSON or None
        uat_json   = data.get("uat_json")    # pre-loaded JSON or None

        # ── Validation ──────────────────────────────────────────────────────
        if brand_key not in BRANDS:
            return jsonify({"status": "error",
                            "message": f"Unknown brand '{brand_key}'. "
                                       f"Valid: {list(BRANDS.keys())}"}), 400

        if not prod_store:
            return jsonify({"status": "error",
                            "message": "prod_store_id is required"}), 400

        brand_cfg = BRANDS[brand_key]

        # Auto-resolve UAT store ID from store_map
        if not uat_store:
            uat_store = brand_cfg.get("store_map", {}).get(prod_store, "")
        if not uat_store and prod_json is None:
            return jsonify({"status": "error",
                            "message": "uat_store_id is required (or configure a "
                                       "store_map entry for this PROD store)"}), 400

        # ── Fetch ────────────────────────────────────────────────────────────
        prod_data, uat_data, prod_url, uat_url = fetch_prod_and_uat(
            brand_cfg,
            prod_store,
            uat_store or prod_store,
            prod_override=prod_json,
            uat_override=uat_json,
        )

        # ── Parse ────────────────────────────────────────────────────────────
        prod_parsed = parse_menu(prod_data)
        uat_parsed  = parse_menu(uat_data)

        # ── Compare ──────────────────────────────────────────────────────────
        meta = {
            "brand":      brand_key,
            "prod_store": prod_store,
            "uat_store":  uat_store,
            "prod_url":   prod_url,
            "uat_url":    uat_url,
        }
        results = compare(prod_parsed, uat_parsed, meta)

        # ── Generate Excel ───────────────────────────────────────────────────
        report_dir = REPORTS_DIR / brand_key
        report_path = report_generator.generate(results, str(report_dir))

        report_id = str(uuid.uuid4())
        _report_store[report_id] = {
            "filepath":    report_path,
            "filename":    os.path.basename(report_path),
            "meta":        results["meta"],
            "prod_parsed": prod_parsed,
            "uat_parsed":  uat_parsed,
        }

        # ── Response ─────────────────────────────────────────────────────────
        return jsonify({
            "status":    "ok",
            "report_id": report_id,
            "filename":  os.path.basename(report_path),
            "meta":      results["meta"],
            "summary":   results["summary"],
            "checks": {
                ck: {
                    "title":  v["title"],
                    "issues": v["issues"],
                    "total":  v["total"],
                    "findings": v.get("findings", []),
                    **{k: v[k] for k in v
                       if k not in ("title", "issues", "total", "findings", "columns")},
                }
                for ck, v in results["checks"].items()
            },
        })

    except Exception as exc:
        tb = traceback.format_exc()
        print(tb, flush=True)
        return jsonify({"status": "error", "message": str(exc), "traceback": tb}), 500


@app.route("/api/download/<report_id>")
def download_report(report_id: str):
    entry = _report_store.get(report_id)
    if not entry:
        abort(404)
    filepath = entry["filepath"]
    if not os.path.exists(filepath):
        abort(404)
    return send_file(
        filepath,
        as_attachment=True,
        download_name=entry["filename"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/api/upload_analyze", methods=["POST"])
def upload_analyze():
    """
    Accepts multipart/form-data with:
      brand           – brand key
      prod_store_id   – optional label
      uat_store_id    – optional label
      prod_file       – JSON file upload
      uat_file        – JSON file upload
    """
    _reload_brands()
    try:
        brand_key  = (request.form.get("brand") or "").upper().strip()
        prod_store = request.form.get("prod_store_id", "PROD").strip()
        uat_store  = request.form.get("uat_store_id", "UAT").strip()

        if brand_key not in BRANDS:
            return jsonify({"status": "error",
                            "message": f"Unknown brand '{brand_key}'"}), 400

        prod_file = request.files.get("prod_file")
        uat_file  = request.files.get("uat_file")

        if not prod_file or not uat_file:
            return jsonify({"status": "error",
                            "message": "Both prod_file and uat_file are required"}), 400

        prod_data = json.loads(prod_file.read().decode("utf-8-sig"))
        uat_data  = json.loads(uat_file.read().decode("utf-8-sig"))

        brand_cfg = BRANDS[brand_key]
        prod_url  = f"[Uploaded: {prod_file.filename}]"
        uat_url   = f"[Uploaded: {uat_file.filename}]"

        prod_parsed = parse_menu(prod_data)
        uat_parsed  = parse_menu(uat_data)

        meta = {
            "brand":      brand_key,
            "prod_store": prod_store,
            "uat_store":  uat_store,
            "prod_url":   prod_url,
            "uat_url":    uat_url,
        }
        results = compare(prod_parsed, uat_parsed, meta)

        report_dir  = REPORTS_DIR / brand_key
        report_path = report_generator.generate(results, str(report_dir))

        report_id = str(uuid.uuid4())
        _report_store[report_id] = {
            "filepath":    report_path,
            "filename":    os.path.basename(report_path),
            "meta":        results["meta"],
            "prod_parsed": prod_parsed,
            "uat_parsed":  uat_parsed,
        }

        return jsonify({
            "status":    "ok",
            "report_id": report_id,
            "filename":  os.path.basename(report_path),
            "meta":      results["meta"],
            "summary":   results["summary"],
            "checks": {
                ck: {
                    "title":  v["title"],
                    "issues": v["issues"],
                    "total":  v["total"],
                    "findings": v.get("findings", []),
                    **{k: v[k] for k in v
                       if k not in ("title", "issues", "total", "findings", "columns")},
                }
                for ck, v in results["checks"].items()
            },
        })

    except Exception as exc:
        tb = traceback.format_exc()
        print(tb, flush=True)
        return jsonify({"status": "error", "message": str(exc), "traceback": tb}), 500


# ── Product Tree API ──────────────────────────────────────────────────────────

@app.route("/api/product_tree", methods=["GET"])
def product_tree():
    """
    Returns the full ingredient/modifier tree for a product in both environments.
    Query params:
      report_id  – the analysis session id
      norm_key   – hash-stripped product key (e.g. 'sweet-chili-crisp')
    """
    report_id = request.args.get("report_id", "")
    norm_key  = request.args.get("norm_key", "").strip()

    entry = _report_store.get(report_id)
    if not entry:
        return jsonify({"status": "error", "message": "Report not found"}), 404
    if not norm_key:
        return jsonify({"status": "error", "message": "norm_key required"}), 400

    prod_parsed = entry.get("prod_parsed", {})
    uat_parsed  = entry.get("uat_parsed",  {})

    def _ref_id(ref):
        return ref.split(".", 1)[1] if "." in ref else ref

    def _resolve_product(parsed, nk):
        """Find the first product whose norm_key matches."""
        import re
        for key, p in parsed.get("products", {}).items():
            if re.sub(r"-[0-9a-f]{8}$", "", key) == nk:
                return key, p
        return None, None

    def _build_tree(parsed, nk):
        key, prod = _resolve_product(parsed, nk)
        if prod is None:
            return None

        raw_groups = parsed.get("product_groups", {})
        raw_mods   = parsed.get("modifier_groups", {}) if "modifier_groups" in parsed else {}
        raw_prods  = parsed.get("products", {})

        def _child_list(group_key, source):
            grp = source.get(group_key, {})
            children = []
            for ref, qty_obj in (grp.get("child_refs") or grp.get("childRefs") or {}).items():
                if not ref.startswith("products."):
                    continue
                pid   = _ref_id(ref)
                child = raw_prods.get(pid, {})
                cal   = child.get("total_calories")
                # qty_obj from the raw childRefs value — min/max may be directly on the
                # object or nested under a "quantity" key depending on API version
                qty_node = (qty_obj or {})
                if "min" not in qty_node and "quantity" in qty_node:
                    qty_node = qty_node.get("quantity") or {}
                children.append({
                    "key":         pid,
                    "name":        child.get("display_name", pid),
                    "price":       child.get("price"),
                    "calories":    cal,
                    "available":   child.get("is_available"),
                    "is_default":  child.get("is_default", False),
                    "qty_min":     qty_node.get("min"),
                    "qty_max":     qty_node.get("max"),
                    "image_url":   child.get("image_url", ""),
                    "tags":        child.get("tags", []),
                })
            return children

        # Ingredient groups
        ingredient_groups = []
        for ref in (prod.get("ingredient_refs") or prod.get("ingredientRefs") or []):
            gid = _ref_id(ref) if isinstance(ref, str) else ref
            grp = raw_groups.get(gid, {})
            if not grp:
                continue
            sel = grp.get("selectionQuantity") or grp.get("selection_quantity") or {}
            ingredient_groups.append({
                "key":      gid,
                "name":     grp.get("displayName") or grp.get("display_name", gid),
                "min":      sel.get("min"),
                "max":      sel.get("max"),
                "children": _child_list(gid, raw_groups),
            })

        # Modifier groups — stored under parsed["modifier_groups"] or raw_mods
        modifier_groups_parsed = parsed.get("modifier_groups", {})
        modifier_groups = []
        for ref in (prod.get("modifier_group_refs") or prod.get("modifierGroupRefs") or []):
            gid = _ref_id(ref) if isinstance(ref, str) else ref
            grp = modifier_groups_parsed.get(gid, {})
            if not grp:
                continue
            sel = grp.get("selectionQuantity") or grp.get("selection_quantity") or {}
            modifier_groups.append({
                "key":  gid,
                "name": grp.get("displayName") or grp.get("display_name", gid),
                "min":  sel.get("min"),
                "max":  sel.get("max"),
                "children": _child_list(gid, modifier_groups_parsed),
            })

        cal = prod.get("total_calories")

        return {
            "key":               key,
            "name":              prod.get("displayName") or prod.get("display_name", ""),
            "description":       prod.get("description", ""),
            "price":             prod.get("price"),
            "calories":          cal,
            "available":         prod.get("isAvailable") or prod.get("is_available"),
            "is_virtual":        prod.get("isVirtual") or prod.get("is_virtual", False),
            "image_url":         prod.get("imageUrl") or prod.get("image_url", ""),
            "ingredient_groups": ingredient_groups,
            "modifier_groups":   modifier_groups,
        }

    return jsonify({
        "status":   "ok",
        "norm_key": norm_key,
        "prod":     _build_tree(prod_parsed, norm_key),
        "uat":      _build_tree(uat_parsed,  norm_key),
    })


# ── History API ───────────────────────────────────────────────────────────────

@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify(_load_history())


@app.route("/api/history", methods=["POST"])
def add_history():
    entry = request.get_json(force=True) or {}
    brand = (entry.get("brand") or "").upper()
    if not brand:
        return jsonify({"status": "error", "message": "brand required"}), 400
    h = _load_history()
    if brand not in h:
        h[brand] = []
    h[brand].insert(0, entry)
    h[brand] = h[brand][:MAX_HISTORY_PER_BRAND]
    _save_history(h)
    total = sum(len(v) for v in h.values())
    return jsonify({"status": "ok", "count": total})


@app.route("/api/history", methods=["DELETE"])
def clear_history_api():
    brand = (request.args.get("brand") or "").upper()
    h = _load_history()
    if brand and brand in h:
        del h[brand]
    else:
        h = {}
    _save_history(h)
    return jsonify({"status": "ok"})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Ensure report dirs exist
    for brand in BRANDS:
        (REPORTS_DIR / brand).mkdir(parents=True, exist_ok=True)

    # Bind to localhost and keep the debugger off unless explicitly opted
    # into — Werkzeug's debugger allows arbitrary code execution if reachable.
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG") == "1"
    print("=" * 60)
    print("  Menu Delta Analyzer  –  Multi-Brand (B1 | B2 | B3)")
    print(f"  http://{host}:5001")
    print("=" * 60)
    app.run(debug=debug, host=host, port=5001)
