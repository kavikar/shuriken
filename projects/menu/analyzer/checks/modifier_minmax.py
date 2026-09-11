"""
Check 4 – Min/Max (selectionQuantity) Declarations

Four sub-checks based on thorough traversal of the IDP menu JSON:

  A. Product Groups  — top-level selectionQuantity on productGroups[]
     (GROUP ALPHA, GROUP BRAVO, GROUP CHARLIE, Size, etc.)  338 UAT / 336 PROD entries.

  B. Modifier Groups — top-level selectionQuantity on modifierGroups[]
     (MODIFIER ALPHA, MODIFIER BRAVO, etc.)  16 entries each in UAT and PROD.

  C. Product Groups – per-Child Ref quantity (min/max) on childRefs[].quantity
     Each child within a productGroup can declare its own quantity range.

  D. Modifier Groups – per-Child Ref quantity (min/max) on childRefs[].quantity
     Each child within a modifierGroup can declare its own quantity range.

Traversal paths confirmed EMPTY for selectionQuantity:
  - products            (no selectionQuantity)
  - alternatives        (not present in any product)
  - ingredientRefs      (ref pointer strings only)
  - modifierGroupRefs   (ref pointer strings only)
  - relatedProducts     (ref pointer strings only)
  - customAttributes.coreProduct  (plain string)
"""
import re


def _fmt(val) -> str:
    return str(val) if val is not None else "—"


def _compare_groups(prod_groups: dict, uat_groups: dict, group_prefix: str = "productGroups.") -> list:
    """Compare two group dicts by dn_key, return findings list."""
    def build_idx(groups):
        idx = {}
        for key, g in groups.items():
            dn = g["dn_key"]
            if dn not in idx:
                idx[dn] = g
        return idx

    prod_idx = build_idx(prod_groups)
    uat_idx  = build_idx(uat_groups)
    findings = []

    for dn in sorted(set(prod_idx) | set(uat_idx)):
        p = prod_idx.get(dn)
        u = uat_idx.get(dn)
        name         = (p or u)["display_name"]
        prod_gid     = (group_prefix + p["key"]) if p else "N/A"
        uat_gid      = (group_prefix + u["key"]) if u else "N/A"

        if p is None:
            findings.append({
                "group":         name,
                "prod_group_id": "N/A",
                "uat_group_id":  uat_gid,
                "prod_min":      "N/A",
                "prod_max":      "N/A",
                "uat_min":       _fmt(u["min"]),
                "uat_max":       _fmt(u["max"]),
                "prod_children": "N/A",
                "uat_children":  u["child_count"],
                "status":        "NEW IN UAT",
            })
        elif u is None:
            findings.append({
                "group":         name,
                "prod_group_id": prod_gid,
                "uat_group_id":  "N/A",
                "prod_min":      _fmt(p["min"]),
                "prod_max":      _fmt(p["max"]),
                "uat_min":       "N/A",
                "uat_max":       "N/A",
                "prod_children": p["child_count"],
                "uat_children":  "N/A",
                "status":        "MISSING IN UAT",
            })
        else:
            changed = (p["min"] != u["min"]) or (p["max"] != u["max"])
            findings.append({
                "group":         name,
                "prod_group_id": prod_gid,
                "uat_group_id":  uat_gid,
                "prod_min":      _fmt(p["min"]),
                "prod_max":      _fmt(p["max"]),
                "uat_min":       _fmt(u["min"]),
                "uat_max":       _fmt(u["max"]),
                "prod_children": p["child_count"],
                "uat_children":  u["child_count"],
                "status":        "MISMATCH" if changed else "MATCH",
            })
    return findings


def _child_norm_key(ref_key: str) -> str:
    """products.option-alpha-56a783f5  →  'option-alpha'  (strip prefix + UUID suffix)"""
    name = ref_key.split(".", 1)[-1] if "." in ref_key else ref_key
    return re.sub(r'-[0-9a-f]{8}$', '', name).lower()


def _child_display(ref_key: str) -> str:
    """products.option-alpha-56a783f5  →  'OPTION ALPHA'  (human-readable)"""
    name = ref_key.split(".", 1)[-1] if "." in ref_key else ref_key
    name = re.sub(r'-[0-9a-f]{8}$', '', name)   # strip UUID
    return name.upper().replace("-", " ")


def _build_reverse_idx(products: dict, ref_field: str) -> dict:
    """
    Invert ingredient_refs / modifier_group_refs into:
        full_group_ref_key  ->  [product display_name, ...]

    e.g. 'productGroups.add-a-side-96d75f77'  ->  ['ITEM ALPHA', ...]
    """
    idx: dict = {}
    for prod in products.values():
        refs = prod.get(ref_field) or set()
        dn   = prod.get("display_name", "")
        for ref_key in refs:
            idx.setdefault(ref_key, []).append(dn) if dn not in idx.get(ref_key, []) else None
    return idx


def _compare_child_quantities(
    prod_groups: dict,
    uat_groups:  dict,
    prod_rev_idx: dict = None,
    uat_rev_idx:  dict = None,
    group_prefix: str  = "productGroups.",
    skip_no_qty:  bool = False,
) -> list:
    """Compare per-child quantity (min/max) inside each group, matched by exact key ID.

    skip_no_qty=True  → omit rows where neither PROD nor UAT declares a quantity (sub-check C)
    skip_no_qty=False → always emit a row, status='NO QTY' when neither side has a value (sub-check D)
    """

    def build_child_idx(child_refs: dict) -> dict:
        idx = {}
        for ref_key, ref_val in (child_refs or {}).items():
            nk  = _child_norm_key(ref_key)
            qty = ((ref_val or {}).get("quantity")) or {}
            idx[nk] = {
                "display": ref_key,
                "min":     qty.get("min"),
                "max":     qty.get("max"),
                "has_qty": bool(qty),
            }
        return idx

    findings = []
    all_keys = sorted(set(prod_groups) | set(uat_groups))

    for key in all_keys:
        p = prod_groups.get(key)
        u = uat_groups.get(key)
        if p is None or u is None:      # group-level missing already flagged in A/B
            continue

        group_id = group_prefix + key   # full prefixed ID

        # used_by: look up this specific key in the reverse index
        used_by = "—"
        if prod_rev_idx is not None or uat_rev_idx is not None:
            ref = group_prefix + key
            names = sorted(
                set((prod_rev_idx or {}).get(ref, [])) |
                set((uat_rev_idx  or {}).get(ref, []))
            )
            used_by = ", ".join(names) if names else "—"

        prod_child_idx = build_child_idx(p.get("child_refs", {}))
        uat_child_idx  = build_child_idx(u.get("child_refs", {}))
        all_children   = sorted(set(prod_child_idx) | set(uat_child_idx))

        for child_nk in all_children:
            pc = prod_child_idx.get(child_nk)
            uc = uat_child_idx.get(child_nk)
            child_name = (pc or uc)["display"]

            if pc is None:
                findings.append({
                    "group":    group_id,
                    "child":    child_name,
                    "used_by":  used_by,
                    "prod_min": "N/A",
                    "prod_max": "N/A",
                    "uat_min":  _fmt(uc["min"]) if uc["has_qty"] else "—",
                    "uat_max":  _fmt(uc["max"]) if uc["has_qty"] else "—",
                    "status":   "NEW IN UAT",
                })
            elif uc is None:
                findings.append({
                    "group":    group_id,
                    "child":    child_name,
                    "used_by":  used_by,
                    "prod_min": _fmt(pc["min"]) if pc["has_qty"] else "—",
                    "prod_max": _fmt(pc["max"]) if pc["has_qty"] else "—",
                    "uat_min":  "N/A",
                    "uat_max":  "N/A",
                    "status":   "MISSING IN UAT",
                })
            else:
                # Both present
                no_qty_either = not pc["has_qty"] and not uc["has_qty"]
                if no_qty_either and skip_no_qty:
                    continue
                changed = (not no_qty_either) and (
                    (pc["min"] != uc["min"]) or (pc["max"] != uc["max"])
                )
                findings.append({
                    "group":    group_id,
                    "child":    child_name,
                    "used_by":  used_by,
                    "prod_min": _fmt(pc["min"]) if pc["has_qty"] else "—",
                    "prod_max": _fmt(pc["max"]) if pc["has_qty"] else "—",
                    "uat_min":  _fmt(uc["min"]) if uc["has_qty"] else "—",
                    "uat_max":  _fmt(uc["max"]) if uc["has_qty"] else "—",
                    "status":   "MISMATCH" if changed else ("NO QTY" if no_qty_either else "MATCH"),
                })
    return findings


def run(prod: dict, uat: dict) -> dict:

    # ---- A. Product Groups (productGroups in raw JSON) ----
    pg_findings = _compare_groups(
        prod.get("product_groups", {}),
        uat.get("product_groups", {}),
        group_prefix="productGroups.",
    )

    # ---- B. Modifier Groups (modifierGroups in raw JSON) ----
    mg_findings = _compare_groups(
        prod.get("modifier_groups", {}),
        uat.get("modifier_groups", {}),
        group_prefix="modifierGroups.",
    )

    # ---- C. Product Groups – per-child quantity ----
    pg_prod_rev = _build_reverse_idx(prod.get("products", {}), "ingredient_refs")
    pg_uat_rev  = _build_reverse_idx(uat.get("products",  {}), "ingredient_refs")
    pg_child_findings = _compare_child_quantities(
        prod.get("product_groups", {}),
        uat.get("product_groups", {}),
        prod_rev_idx=pg_prod_rev,
        uat_rev_idx=pg_uat_rev,
        group_prefix="productGroups.",
        skip_no_qty=True,       # product group children without qty are expected – skip them
    )

    # ---- D. Modifier Groups – per-child quantity ----
    mg_prod_rev = _build_reverse_idx(prod.get("products", {}), "modifier_group_refs")
    mg_uat_rev  = _build_reverse_idx(uat.get("products",  {}), "modifier_group_refs")
    mg_child_findings = _compare_child_quantities(
        prod.get("modifier_groups", {}),
        uat.get("modifier_groups", {}),
        prod_rev_idx=mg_prod_rev,
        uat_rev_idx=mg_uat_rev,
        group_prefix="modifierGroups.",
        skip_no_qty=False,      # show ALL modifier children, even those with no qty declared
    )

    pg_issues       = sum(1 for f in pg_findings       if f["status"] not in ("MATCH",))
    mg_issues       = sum(1 for f in mg_findings       if f["status"] not in ("MATCH",))
    pg_child_issues = sum(1 for f in pg_child_findings if f["status"] not in ("MATCH", "NO QTY"))
    mg_child_issues = sum(1 for f in mg_child_findings if f["status"] not in ("MATCH", "NO QTY"))
    total_issues    = pg_issues + mg_issues + pg_child_issues + mg_child_issues

    sub_checks = [
        {
            "subtitle": "A. Product Groups – selectionQuantity (min / max)",
            "findings": pg_findings,
            "total":    len(pg_findings),
            "issues":   pg_issues,
        },
        {
            "subtitle": "B. Modifier Groups – selectionQuantity (min / max)",
            "findings": mg_findings,
            "total":    len(mg_findings),
            "issues":   mg_issues,
        },
        {
            "subtitle": "C. Product Groups – childRef quantity (per-child min / max)",
            "findings": pg_child_findings,
            "total":    len(pg_child_findings),
            "issues":   pg_child_issues,
        },
        {
            "subtitle": "D. Modifier Groups – childRef quantity (per-child min / max)",
            "findings": mg_child_findings,
            "total":    len(mg_child_findings),
            "issues":   mg_child_issues,
        },
    ]

    flat_findings = (
        [dict(object_type="Product Group",         **f) for f in pg_findings] +
        [dict(object_type="Modifier Group",        **f) for f in mg_findings] +
        [dict(object_type="PG Child Qty",          **f) for f in pg_child_findings] +
        [dict(object_type="MG Child Qty",          **f) for f in mg_child_findings]
    )

    return {
        "title":      "Min/Max (selectionQuantity) Declarations",
        "sub_checks": sub_checks,
        "findings":   flat_findings,
        "issues":     total_issues,
        "total":      len(flat_findings),
    }
