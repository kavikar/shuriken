"""
Check 8 – Non-Virtual Attributes (Price / Availability / Calories)
For every item where isVirtual=false in either environment, compare:
  - price
  - isAvailable
  - totalCalories (from nutrition.totalCalories)

Covers all reachable products via:
  1. Direct top-level products
  2. alternatives{}
  3. ingredientRefs{} → productGroups → childRefs → products
  4. modifierGroupRefs{} → productGroups → childRefs → products
  5. relatedProducts{}
  6. customAttributes.coreProduct
"""


def _fmt_price(val) -> str:
    if val is None:
        return "N/A"
    try:
        return f"${float(val):.2f}"
    except Exception:
        return str(val)


def _fmt_cal(val) -> str:
    if val is None:
        return "N/A"
    return str(val)


def _is_empty_price(val) -> bool:
    """True only if price is completely absent from the API (None)."""
    return val is None


def _is_empty_cal(val) -> bool:
    """True only if calories is completely absent from the API (None)."""
    return val is None


def _fmt_avail(val) -> str:
    if val is None:
        return "MISSING"
    return "Yes" if val else "No"


def _price_status(p_val, u_val) -> str:
    p_missing = p_val is None
    u_missing = u_val is None
    # Both absent → no issue
    if p_missing and u_missing:
        return "MATCH"
    # One side completely missing (None)
    if p_missing and not u_missing:
        return "MISSING IN PROD"
    if not p_missing and u_missing:
        return "MISSING IN UAT"
    # Both have values — compare
    try:
        p_f = round(float(p_val), 2)
        u_f = round(float(u_val), 2)
        if p_f == u_f:
            return "MATCH"
        # One side is $0.00 while the other has a real price → critical
        if p_f == 0.0 and u_f != 0.0:
            return "ZERO IN PROD"
        if u_f == 0.0 and p_f != 0.0:
            return "ZERO IN UAT"
        # Large gap (≥$20) → critical
        if abs(p_f - u_f) >= 20.0:
            return "PRICE MISMATCH"
        # Small gap (<$20) → informational only, not a warning
        return "PRICE VARIANCE"
    except Exception:
        if p_val != u_val:
            return "PRICE MISMATCH"
    return "MATCH"


def _cal_status(p_val, u_val) -> str:
    p_missing = p_val is None
    u_missing = u_val is None
    # Both absent → no issue
    if p_missing and u_missing:
        return "MATCH"
    # One side completely missing
    if p_missing and not u_missing:
        return "MISSING IN PROD"
    if not p_missing and u_missing:
        return "MISSING IN UAT"
    if p_val != u_val:
        return "MISMATCH"
    return "MATCH"


def _field_status(p_val, u_val) -> str:
    """Generic field status for availability (boolean)."""
    if p_val is None and u_val is None:
        return "MATCH"
    if p_val is None:
        return "MISSING IN PROD"
    if u_val is None:
        return "MISSING IN UAT"
    if p_val != u_val:
        return "MISMATCH"
    return "MATCH"


def _overall_status(price_st: str, avail_st: str, cal_st: str) -> str:
    # Any of these → CRITICAL regardless of other fields
    critical = {
        "MISSING IN UAT", "MISSING IN PROD",
        "ZERO IN PROD",   "ZERO IN UAT",
        "PRICE MISMATCH",
    }
    # Availability / calorie mismatch → WARNING
    warn = {"MISMATCH"}
    # "PRICE VARIANCE" (< $20 gap) is purely informational — no status escalation
    for st in (price_st, avail_st, cal_st):
        if st in critical:
            return "CRITICAL"
    for st in (price_st, avail_st, cal_st):
        if st in warn:
            return "WARNING"
    return "OK"


def _ref_id(ref: str) -> str:
    """Strip type prefix: 'products.bun-39b63ffb' -> 'bun-39b63ffb'"""
    return ref.split(".", 1)[1] if "." in ref else ref


def _build_usage_index(parsed: dict) -> dict:
    """
    Returns {product_key: [parent display names]} by scanning:
      - categories.child_refs
      - product_groups.child_refs
    """
    usage: dict = {}

    def _add(prod_key, parent_name):
        usage.setdefault(prod_key, []).append(parent_name)

    # Build reverse map: group_id → [parent product display names]
    # A group (e.g. GROUP ALPHA) can be referenced by many parent products
    # (e.g. ITEM ALPHA, ITEM BRAVO…). We collect all of them
    # so we can show the full traceback: child → group → parent product(s).
    # Covers ingredientRefs, modifierGroupRefs AND relatedProducts.alternatives.
    group_to_parents: dict = {}
    for p in parsed.get("products", {}).values():
        pname = p.get("display_name") or "?"
        for ref in (p.get("ingredient_refs") or set()):
            gid = _ref_id(ref) if "." in ref else ref
            group_to_parents.setdefault(gid, []).append(pname)
        for ref in (p.get("modifier_group_refs") or set()):
            gid = _ref_id(ref) if "." in ref else ref
            group_to_parents.setdefault(gid, []).append(pname)
        # relatedProducts.alternatives also references product groups
        for ref in (p.get("alt_group_refs") or set()):
            gid = _ref_id(ref) if "." in ref else ref
            group_to_parents.setdefault(gid, []).append(pname)

    def _parent_suffix(gkey: str) -> str:
        parents = group_to_parents.get(gkey, [])
        if not parents:
            return ""
        # Deduplicate while preserving order — always return full list
        seen, unique = set(), []
        for p in parents:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return " → " + ", ".join(unique)

    for cat in parsed.get("categories", {}).values():
        dn  = cat.get("display_name") or cat.get("displayName", "?")
        kid = "categories." + cat.get("key", "?")
        for ref in (cat.get("child_refs") or {}).keys():
            if ref.startswith("products."):
                _add(_ref_id(ref), f"[Cat] {dn} ({kid})")

    for grp in parsed.get("product_groups", {}).values():
        dn   = grp.get("display_name") or grp.get("displayName", "?")
        gkey = grp.get("key", "?")
        kid  = "productGroups." + gkey
        suffix = _parent_suffix(gkey)
        for ref in (grp.get("child_refs") or {}).keys():
            if ref.startswith("products."):
                _add(_ref_id(ref), f"[Group] {dn} ({kid}){suffix}")

    return usage


def run(prod: dict, uat: dict) -> dict:

    import re as _re

    def _strip_hash(key: str) -> str:
        """Strip trailing 8-char hex hash: option-alpha-ccda6ecf -> option-alpha."""
        return _re.sub(r'-[0-9a-f]{8}$', '', key)

    def _count_child_avail_diffs(p_prod_entry, u_prod_entry):
        """Return (diff_count, detail_str) comparing child availability across
        all ingredient/modifier groups shared by both PROD and UAT products."""
        if not p_prod_entry or not u_prod_entry:
            return 0, ""
        prod_groups = prod.get("product_groups", {})
        uat_groups  = uat.get("product_groups", {})
        prod_prods  = prod.get("products", {})
        uat_prods   = uat.get("products", {})

        all_group_refs = (
            set(p_prod_entry.get("ingredient_refs") or set()) |
            set(p_prod_entry.get("modifier_group_refs") or set())
        )

        diff_count = 0
        diff_items = []
        for ref in all_group_refs:
            gid   = _ref_id(ref) if "." in ref else ref
            p_grp = prod_groups.get(gid, {})
            u_grp = uat_groups.get(gid, {})
            if not p_grp or not u_grp:
                continue
            # Build stripped-key → is_available for PROD children
            p_child_avail = {}
            for cref in (p_grp.get("child_refs") or {}).keys():
                if not cref.startswith("products."):
                    continue
                cid = _ref_id(cref)
                nk  = _strip_hash(cid)
                cp  = prod_prods.get(cid, {})
                p_child_avail[nk] = cp.get("is_available")
            # Compare with UAT children
            for cref in (u_grp.get("child_refs") or {}).keys():
                if not cref.startswith("products."):
                    continue
                cid    = _ref_id(cref)
                nk     = _strip_hash(cid)
                cu     = uat_prods.get(cid, {})
                u_avail = cu.get("is_available")
                p_avail = p_child_avail.get(nk)
                if p_avail is not None and u_avail is not None and p_avail != u_avail:
                    diff_count += 1
                    diff_items.append(cu.get("display_name") or nk)
        detail = ", ".join(dict.fromkeys(diff_items))
        return diff_count, detail

    # Build index keyed by norm_key (hash-stripped base name) so that every
    # distinct product variant (e.g. item-alpha vs item-alpha-copy)
    # gets its own row instead of being collapsed by display name.
    # When multiple raw keys share the same norm_key (the same option appearing in
    # 30 modifier groups), the first encountered entry is the representative row.
    def build_non_virtual_idx(parsed):
        idx = {}
        for key, p in parsed.get("products", {}).items():
            if p.get("is_virtual", True):
                continue
            nk = p["norm_key"]
            if nk not in idx:
                idx[nk] = {
                    "display_name":   p["display_name"],
                    "norm_key":       nk,
                    "prod_key":       "products." + p["key"],
                    "is_recipe":      p.get("is_recipe", False),
                    "price":          p.get("price"),
                    "is_available":   p.get("is_available"),
                    "total_calories": p.get("total_calories"),
                    "is_default":     p.get("is_default", False),
                }
        return idx

    prod_idx = build_non_virtual_idx(prod)
    uat_idx  = build_non_virtual_idx(uat)

    prod_usage = _build_usage_index(prod)
    uat_usage  = _build_usage_index(uat)

    def _used_by(raw_key: str, usage: dict) -> str:
        key = _ref_id(raw_key) if "." in raw_key else raw_key
        parents = usage.get(key, [])
        # Deduplicate while preserving order
        seen = set()
        unique = [p for p in parents if not (p in seen or seen.add(p))]
        return ", ".join(unique) if unique else "—"

    # All distinct norm_keys across both environments
    all_norm_keys = sorted(set(prod_idx) | set(uat_idx))

    # Detect display names shared by multiple norm_keys — need disambiguation
    dn_to_nks: dict = {}
    for nk in all_norm_keys:
        dn = (prod_idx.get(nk) or uat_idx.get(nk))["display_name"]
        dn_to_nks.setdefault(dn, []).append(nk)
    ambiguous_dns = {dn for dn, nks in dn_to_nks.items() if len(nks) > 1}

    def _product_label(display_name: str, norm_key: str) -> str:
        """Append norm_key in brackets only when the display name is ambiguous."""
        if display_name in ambiguous_dns:
            return f"{display_name} ({norm_key})"
        return display_name

    findings = []

    for nk in all_norm_keys:
        p = prod_idx.get(nk)
        u = uat_idx.get(nk)
        base      = p or u
        name      = _product_label(base["display_name"], nk)
        is_recipe = base.get("is_recipe", False)

        if p is None:
            # Exists only in UAT as non-virtual
            u_key = u.get("prod_key", "")
            findings.append({
                "product": name,
                "norm_key": nk,
                "prod_id": "N/A",
                "uat_id":  u_key,
                "id_status": "N/A",
                "prod_used_by": "N/A",
                "uat_used_by": _used_by(u_key, uat_usage),
                "object_type": "Recipe" if is_recipe else "Product",
                "prod_price": "N/A",
                "uat_price": _fmt_price(u["price"]),
                "price_status": "N/A (NEW)",
                "prod_availability": "N/A",
                "uat_availability": _fmt_avail(u["is_available"]),
                "availability_status": "N/A (NEW)",
                "prod_calories": "N/A",
                "uat_calories": _fmt_cal(u["total_calories"]),
                "calories_status": "N/A (NEW)",
                "overall_status": "NEW IN UAT",
            })
            continue

        if u is None:
            # Exists only in PROD as non-virtual
            p_key = p.get("prod_key", "")
            findings.append({
                "product": name,
                "norm_key": nk,
                "prod_id": p_key,
                "uat_id":  "N/A",
                "id_status": "N/A",
                "prod_used_by": _used_by(p_key, prod_usage),
                "uat_used_by": "N/A",
                "object_type": "Recipe" if is_recipe else "Product",
                "prod_price": _fmt_price(p["price"]),
                "uat_price": "N/A",
                "price_status": "N/A (REMOVED)",
                "prod_availability": _fmt_avail(p["is_available"]),
                "uat_availability": "N/A",
                "availability_status": "N/A (REMOVED)",
                "prod_calories": _fmt_cal(p["total_calories"]),
                "uat_calories": "N/A",
                "calories_status": "N/A (REMOVED)",
                "overall_status": "REMOVED FROM UAT",
            })
            continue

        price_st = _price_status(p["price"], u["price"])
        avail_st = _field_status(p["is_available"], u["is_available"])
        cal_st   = _cal_status(p["total_calories"], u["total_calories"])
        p_key    = p.get("prod_key", "")
        u_key    = u.get("prod_key", "")

        # Count child-level availability diffs (ingredient/modifier group children)
        p_full = prod.get("products", {}).get(_ref_id(p_key) if "." in p_key else p_key, {})
        u_full = uat.get("products", {}).get(_ref_id(u_key) if "." in u_key else u_key, {})
        child_diff_count, child_diff_detail = _count_child_avail_diffs(p_full, u_full)

        # Matched by norm_key — full keys always differ across environments by
        # design (IDP assigns env-specific hashes), so ID Status is always SAME ID.
        id_st   = "SAME ID"
        overall = _overall_status(price_st, avail_st, cal_st)
        # Escalate to WARNING if ingredient children have availability diffs
        if overall == "OK" and child_diff_count > 0:
            overall = "WARNING"

        findings.append({
            "product": name,
            "norm_key": nk,
            "prod_id": p_key,
            "uat_id":  u_key,
            "id_status": id_st,
            "prod_used_by": _used_by(p_key, prod_usage),
            "uat_used_by":  _used_by(u_key, uat_usage),
            "object_type": "Recipe" if is_recipe else "Product",
            "prod_price": _fmt_price(p["price"]),
            "uat_price": _fmt_price(u["price"]),
            "price_status": price_st,
            "prod_availability": _fmt_avail(p["is_available"]),
            "uat_availability": _fmt_avail(u["is_available"]),
            "availability_status": avail_st,
            "prod_calories": _fmt_cal(p["total_calories"]),
            "uat_calories": _fmt_cal(u["total_calories"]),
            "calories_status": cal_st,
            "child_avail_issues": child_diff_count,
            "child_avail_detail": child_diff_detail,
            "overall_status": overall,
        })

    # Sort: CRITICAL first, then WARNING, then OK
    order = {"CRITICAL": 0, "WARNING": 1, "NEW IN UAT": 2, "REMOVED FROM UAT": 3, "OK": 4}
    findings.sort(key=lambda x: (order.get(x["overall_status"], 5), x["product"]))

    critical = sum(1 for f in findings if f["overall_status"] == "CRITICAL")
    warnings = sum(1 for f in findings if f["overall_status"] == "WARNING")

    return {
        "title": "Non-Virtual Attributes: Price / Availability / Calories",
        "columns": [
            "Product",
            "PROD ID", "UAT ID", "ID Status",
            "PROD Used By", "UAT Used By",
            "Object Type",
            "PROD Price", "UAT Price", "Price Status",
            "PROD Availability", "UAT Availability", "Availability Status",
            "PROD Calories", "UAT Calories", "Calorie Status",
            "Overall Status",
        ],
        "findings": findings,
        "issues": critical + warnings,
        "critical": critical,
        "warnings": warnings,
        "total": len(findings),
    }
