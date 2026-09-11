"""
Check 6 – Ordering / Sequence (All 4 Levels)

Traversal path (example):
  MAIN (root category)
   └─ childRefs → [sub-categories…]                        ← Sub-check A
         └─ CATEGORY ALPHA → childRefs → [products…]        ← Sub-check B
               └─ ITEM ALPHA
                     ├─ ingredientRefs  → [productGroups…]  ┐
                     └─ modifierGroupRefs → [modGroups…]    ┘ Sub-check C
                           └─ GROUP ALPHA → childRefs → [Option One…]  ← Sub-check D

Sub-check A – Menu Page     : order of sub-categories within each parent category
Sub-check B – Product List  : order of products within each leaf category
Sub-check C – Product Detail: order of ingredientRefs + modifierGroupRefs on each product
Sub-check D – Group Children: order of options inside each productGroup + modifierGroup
"""


def _order_diff(prod_order: list, uat_order: list) -> str:
    if prod_order == uat_order:
        return "MATCH"
    added     = [c for c in uat_order if c not in prod_order]
    removed   = [c for c in prod_order if c not in uat_order]
    reordered = (sorted(prod_order) == sorted(uat_order)) and (prod_order != uat_order)
    parts = []
    if added:     parts.append(f"+{len(added)} added")
    if removed:   parts.append(f"-{len(removed)} removed")
    if reordered: parts.append("reordered")
    return " | ".join(parts) if parts else "MISMATCH"


def _fmt(seq: list, limit: int = 50) -> str:
    items = [str(s) for s in seq]
    tail  = "…" if len(items) > limit else ""
    return " → ".join(items[:limit]) + tail


def _build_idx(obj_dict: dict) -> dict:
    """Index objects by dn_key, first-occurrence wins."""
    idx = {}
    for obj in obj_dict.values():
        k = obj["dn_key"]
        if k not in idx:
            idx[k] = obj
    return idx


def _build_group_usage_index(parsed: dict) -> dict:
    """
    Returns {group_key: [product display names that reference it]}
    via ingredientRefs and modifierGroupRefs.
    """
    usage: dict = {}
    for prod in parsed.get("products", {}).values():
        pdn = prod.get("display_name", "?")
        for ref in prod.get("ingredient_refs", set()) | prod.get("modifier_group_refs", set()):
            gk = ref.split(".", 1)[1] if "." in ref else ref
            usage.setdefault(gk, []).append(pdn)
    return usage


def _used_by_str(key: str, usage: dict) -> str:
    parents = usage.get(key, [])
    seen = set()
    unique = [p for p in parents if not (p in seen or seen.add(p))]
    return ", ".join(unique) if unique else "\u2014"


def run(prod: dict, uat: dict) -> dict:

    # ── Sub-check A: Menu Page – sub-category navigation order ──────────────
    prod_cat_idx = _build_idx(prod.get("categories", {}))
    uat_cat_idx  = _build_idx(uat.get("categories",  {}))

    a_findings = []
    for dn in sorted(set(prod_cat_idx) | set(uat_cat_idx)):
        p = prod_cat_idx.get(dn)
        u = uat_cat_idx.get(dn)
        if p is None or u is None:
            continue
        p_order = p.get("category_children_dn_keys", [])
        u_order = u.get("category_children_dn_keys", [])
        if not p_order and not u_order:
            continue                # leaf categories have no sub-cat children
        diff = _order_diff(p_order, u_order)
        a_findings.append({
            "parent_category": (p or u)["display_name"],
            "prod_count":      len(p_order),
            "uat_count":       len(u_order),
            "prod_order":      _fmt(p_order),
            "uat_order":       _fmt(u_order),
            "diff_summary":    diff,
            "status":          "MATCH" if diff == "MATCH" else "MISMATCH",
        })

    # ── Sub-check B: Products List Page – product sequence within category ───
    b_findings = []
    for dn in sorted(set(prod_cat_idx) | set(uat_cat_idx)):
        p = prod_cat_idx.get(dn)
        u = uat_cat_idx.get(dn)
        if p is None or u is None:
            continue
        p_order = p.get("product_children_dn_keys", [])
        u_order = u.get("product_children_dn_keys", [])
        if not p_order and not u_order:
            continue                # container categories with no direct products
        diff = _order_diff(p_order, u_order)
        b_findings.append({
            "category":     (p or u)["display_name"],
            "prod_count":   len(p_order),
            "uat_count":    len(u_order),
            "prod_order":   _fmt(p_order),
            "uat_order":    _fmt(u_order),
            "diff_summary": diff,
            "status":       "MATCH" if diff == "MATCH" else "MISMATCH",
        })

    # ── Sub-check C: Product Detail – ingredientRefs + modifierGroupRefs order
    prod_prod_idx = _build_idx(prod.get("products", {}))
    uat_prod_idx  = _build_idx(uat.get("products",  {}))

    c_findings = []
    for dn in sorted(set(prod_prod_idx) | set(uat_prod_idx)):
        pp = prod_prod_idx.get(dn)
        up = uat_prod_idx.get(dn)
        if pp is None or up is None:
            continue
        name = (pp or up)["display_name"]

        p_ing = pp.get("ingredient_group_names", [])
        u_ing = up.get("ingredient_group_names", [])
        p_mod = pp.get("modifier_group_names", [])
        u_mod = up.get("modifier_group_names", [])

        # Skip products with no refs at all
        if not p_ing and not u_ing and not p_mod and not u_mod:
            continue

        ing_diff = _order_diff(p_ing, u_ing) if (p_ing or u_ing) else "N/A"
        mod_diff = _order_diff(p_mod, u_mod) if (p_mod or u_mod) else "N/A"
        overall  = "MATCH" if (ing_diff in ("MATCH", "N/A") and mod_diff in ("MATCH", "N/A")) else "MISMATCH"

        c_findings.append({
            "prod_id":         "products." + pp["key"] if pp else "N/A",
            "uat_id":          "products." + up["key"] if up else "N/A",
            "prod_ing_order":  _fmt(p_ing),
            "uat_ing_order":   _fmt(u_ing),
            "prod_mod_order":  _fmt(p_mod),
            "uat_mod_order":   _fmt(u_mod),
            "ing_diff":        ing_diff,
            "mod_diff":        mod_diff,
            "status":          overall,
        })

    # ── Sub-check D: Group Children – options sequence ───────────────────────
    prod_pg_idx = _build_idx(prod.get("product_groups",  {}))
    uat_pg_idx  = _build_idx(uat.get("product_groups",   {}))
    prod_mg_idx = _build_idx(prod.get("modifier_groups", {}))
    uat_mg_idx  = _build_idx(uat.get("modifier_groups",  {}))

    prod_grp_usage = _build_group_usage_index(prod)
    uat_grp_usage  = _build_group_usage_index(uat)

    d_findings = []

    # ProductGroups (ingredientRefs children)
    for dn in sorted(set(prod_pg_idx) | set(uat_pg_idx)):
        p = prod_pg_idx.get(dn)
        u = uat_pg_idx.get(dn)
        if p is None or u is None:
            continue
        p_order = p.get("child_display_names", p.get("child_norm_names", []))
        u_order = u.get("child_display_names", u.get("child_norm_names", []))
        p_ids   = p.get("child_norm_names", [])
        u_ids   = u.get("child_norm_names", [])
        diff = _order_diff(p_order, u_order)
        p_gid = "productGroups." + p["key"]
        u_gid = "productGroups." + u["key"]
        d_findings.append({
            "group_name":    (p or u)["display_name"],
            "prod_group_id": p_gid,
            "uat_group_id":  u_gid,
            "used_by":       _used_by_str(p["key"], prod_grp_usage) or _used_by_str(u["key"], uat_grp_usage),
            "prod_count":    len(p_order),
            "uat_count":     len(u_order),
            "prod_order":    _fmt(p_order),
            "uat_order":     _fmt(u_order),
            "diff_summary":  diff,
            "status":        "MATCH" if diff == "MATCH" else "MISMATCH",
        })

    # ModifierGroups (modifierGroupRefs children)
    for dn in sorted(set(prod_mg_idx) | set(uat_mg_idx)):
        p = prod_mg_idx.get(dn)
        u = uat_mg_idx.get(dn)
        if p is None or u is None:
            continue
        p_order = p.get("child_display_names", [])
        u_order = u.get("child_display_names", [])
        p_ids   = p.get("child_norm_names", [])
        u_ids   = u.get("child_norm_names", [])
        diff = _order_diff(p_order, u_order)
        p_gid = "modifierGroups." + p["key"]
        u_gid = "modifierGroups." + u["key"]
        d_findings.append({
            "group_name":    (p or u)["display_name"],
            "prod_group_id": p_gid,
            "uat_group_id":  u_gid,
            "used_by":       _used_by_str(p["key"], prod_grp_usage) or _used_by_str(u["key"], uat_grp_usage),
            "prod_count":    len(p_order),
            "uat_count":     len(u_order),
            "prod_order":    _fmt(p_order),
            "uat_order":     _fmt(u_order),
            "diff_summary":  diff,
            "status":        "MATCH" if diff == "MATCH" else "MISMATCH",
        })

    # ── Totals ───────────────────────────────────────────────────────────────
    a_issues = sum(1 for f in a_findings if f["status"] != "MATCH")
    b_issues = sum(1 for f in b_findings if f["status"] != "MATCH")
    c_issues = sum(1 for f in c_findings if f["status"] != "MATCH")
    d_issues = sum(1 for f in d_findings if f["status"] != "MATCH")
    total_issues = a_issues + b_issues + c_issues + d_issues

    flat = (
        [dict(level="A – Cat Nav",        **f) for f in a_findings] +
        [dict(level="B – Product List",   **f) for f in b_findings] +
        [dict(level="C – Product Detail", **f) for f in c_findings] +
        [dict(level="D – Group Children", **f) for f in d_findings]
    )

    sub_checks = [
        {
            "subtitle": "A – Menu Page: Sub-Category Navigation Order",
            "findings": a_findings,
            "total":    len(a_findings),
            "issues":   a_issues,
        },
        {
            "subtitle": "B – Products List Page: Product Sequence within Category",
            "findings": b_findings,
            "total":    len(b_findings),
            "issues":   b_issues,
        },
        {
            "subtitle": "C – Product Detail Page: ingredientRefs & modifierGroupRefs Order",
            "findings": c_findings,
            "total":    len(c_findings),
            "issues":   c_issues,
        },
        {
            "subtitle": "D – Group Children: Options Sequence (ProductGroups & ModifierGroups)",
            "findings": d_findings,
            "total":    len(d_findings),
            "issues":   d_issues,
        },
    ]

    return {
        "title":      "Ordering / Sequence – All Levels",
        "sub_checks": sub_checks,
        "findings":   flat,
        "issues":     total_issues,
        "total":      len(flat),
    }
