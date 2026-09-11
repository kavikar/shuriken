"""
Check 2 – Ingredient Differences per Product / Modifier

Follows: product → ingredientRefs → productGroups → childRefs → ingredient products
Diffs are grouped by product group display name so each group appears on its own row.
"""


def _ref_id(ref: str) -> str:
    return ref.split(".", 1)[1] if "." in ref else ref


def _build_usage_index(parsed: dict) -> dict:
    """
    Returns {product_key: [category display names]}.

    Resolves two levels:
      Level 1 – direct: product is a direct child of a category.
      Level 2 – indirect: product is a child of a productGroup whose
                parent product(s) belong to a category.
                Chain: category → product.child_refs
                              → product.ingredient_refs (productGroup)
                              → productGroup.child_refs (ingredient product)
    """
    usage: dict = {}

    def _add(pid, cat_name):
        lst = usage.setdefault(pid, [])
        if cat_name not in lst:
            lst.append(cat_name)

    categories     = parsed.get("categories", {})
    product_groups = parsed.get("product_groups", {})
    products       = parsed.get("products", {})

    # Level 1: category → direct child products
    prod_to_cats: dict = {}
    for cat in categories.values():
        dn = cat.get("display_name") or "?"
        for ref in (cat.get("child_refs") or {}).keys():
            if ref.startswith("products."):
                pid = _ref_id(ref)
                prod_to_cats.setdefault(pid, [])
                if dn not in prod_to_cats[pid]:
                    prod_to_cats[pid].append(dn)
                _add(pid, dn)

    # Level 2: category-member product → its ingredient productGroups AND
    #           relatedProducts.alternatives groups → their children inherit the category
    group_to_cats: dict = {}
    for pid, cats in prod_to_cats.items():
        p = products.get(pid)
        if not p:
            continue
        all_group_refs = (p.get("ingredient_refs") or set()) | (p.get("alt_group_refs") or set())
        for ref in all_group_refs:
            grp_key = _ref_id(ref)
            for cat_name in cats:
                group_to_cats.setdefault(grp_key, set()).add(cat_name)

    for grp_key, cat_names in group_to_cats.items():
        grp = product_groups.get(grp_key)
        if not grp:
            continue
        for ref in (grp.get("child_refs") or {}).keys():
            if ref.startswith("products."):
                for cat_name in sorted(cat_names):
                    _add(_ref_id(ref), cat_name)

    return usage


def _get_by_group(p: dict, groups: dict, products: dict) -> dict:
    """
    Returns {group_display_name: set_of_ingredient_names (uppercased)}.
    """
    by_group: dict = {}
    for ref in p.get("ingredient_refs", set()):
        grp = groups.get(_ref_id(ref))
        if not grp:
            continue
        grp_name = (grp.get("display_name") or "").strip() or _ref_id(ref)
        names: set = set()
        for child_ref in (grp.get("child_refs") or {}).keys():
            if child_ref.startswith("products."):
                ing_prod = products.get(_ref_id(child_ref))
                if ing_prod:
                    names.add(ing_prod["display_name"].strip().upper())
        if names:
            by_group.setdefault(grp_name, set()).update(names)
    return by_group


def _grouped_list(by_group: dict) -> list:
    """Convert {group: set} → sorted list of {group, items} dicts."""
    return [
        {"group": grp, "items": sorted(names)}
        for grp, names in sorted(by_group.items())
        if names
    ]


def run(prod: dict, uat: dict) -> dict:
    prod_prods  = prod.get("products", {})
    uat_prods   = uat.get("products", {})
    prod_groups = prod.get("product_groups", {})
    uat_groups  = uat.get("product_groups", {})

    prod_usage = _build_usage_index(prod)
    uat_usage  = _build_usage_index(uat)

    def _used_by(prod_key: str, uat_key: str) -> str:
        p_parents = prod_usage.get(prod_key, []) if prod_key else []
        u_parents = uat_usage.get(uat_key,  []) if uat_key  else []
        seen = set()
        unique = [x for x in (p_parents + u_parents) if not (x in seen or seen.add(x))]
        return ", ".join(unique) if unique else "—"

    def build_index(prods, groups, products):
        """Index by exact full product key — no name-based merging."""
        idx = {}
        for key, p in prods.items():
            if not p.get("ingredient_refs"):
                continue
            by_group = _get_by_group(p, groups, products)
            if not by_group:
                continue
            idx[key] = {
                "display_name": p["display_name"],
                "full_key":     key,
                "dn_key":       p["dn_key"],
                "by_group":     by_group,
            }
        return idx

    prod_idx = build_index(prod_prods, prod_groups, prod_prods)
    uat_idx  = build_index(uat_prods,  uat_groups,  uat_prods)

    all_keys = sorted(set(prod_idx) | set(uat_idx))
    findings = []

    for dn in all_keys:
        p = prod_idx.get(dn)
        u = uat_idx.get(dn)
        display  = (p or u)["display_name"]
        prod_key = p["full_key"] if p else ""
        uat_key  = u["full_key"] if u else ""
        dn       = (p or u)["dn_key"]
        used_by  = _used_by(prod_key, uat_key)


        if p is None:
            u_total = sum(len(s) for s in u["by_group"].values())
            findings.append({
                "product":    display,
                "prod_key":   prod_key,
                "uat_key":    uat_key,
                "used_by":    used_by,
                "prod_count": 0,
                "uat_count":  u_total,
                "removed":    [],
                "status":     "NEW IN UAT",
                "added":      _grouped_list(u["by_group"]),
            })
            continue

        if u is None:
            p_total = sum(len(s) for s in p["by_group"].values())
            findings.append({
                "product":    display,
                "prod_key":   prod_key,
                "uat_key":    uat_key,
                "used_by":    used_by,
                "prod_count": p_total,
                "uat_count":  0,
                "removed":    _grouped_list(p["by_group"]),
                "status":     "MISSING IN UAT",
                "added":      [],
            })
            continue

        # Per-group diff
        all_groups = sorted(set(p["by_group"]) | set(u["by_group"]))
        added_groups   = []
        removed_groups = []
        for grp in all_groups:
            p_names = p["by_group"].get(grp, set())
            u_names = u["by_group"].get(grp, set())
            added   = sorted(u_names - p_names)
            removed = sorted(p_names - u_names)
            if added:
                added_groups.append({"group": grp, "items": added})
            if removed:
                removed_groups.append({"group": grp, "items": removed})

        p_total = sum(len(s) for s in p["by_group"].values())
        u_total = sum(len(s) for s in u["by_group"].values())
        status  = "CHANGED" if (added_groups or removed_groups) else "MATCH"
        findings.append({
            "product":    display,
            "prod_key":   prod_key,
            "uat_key":    uat_key,
            "used_by":    used_by,
            "prod_count": p_total,
            "uat_count":  u_total,
            "removed":    removed_groups,
            "status":     status,
            "added":      added_groups,
        })

    issues = sum(1 for f in findings if f["status"] != "MATCH")
    return {
        "title":    "Ingredient Differences per Product / Modifier",
        "columns":  ["PROD Product ID", "UAT Product ID", "Displayed In (Categories)",
                     "PROD Count", "UAT Count",
                     "Only in PROD", "Status", "Only in UAT"],
        "findings": findings,
        "issues":   issues,
        "total":    len(findings),
    }


