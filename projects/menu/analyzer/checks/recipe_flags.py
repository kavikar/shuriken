"""
Check 3 – isRecipe & isDefault Flag Mismatches

Three sub-checks rendered as separate tables:
  A. Products – isRecipe & isDefault  (deep traversal via all_products)
     NOTE: Products carry BOTH flags. All other traversal paths (ingredientRefs,
     modifierGroupRefs, relatedProducts, alternatives, customAttributes.coreProduct)
     are reference pointer sets/strings only — no flags are embedded in them.
  B. Modifier Groups – isRecipe (all productGroups; no isDefault on groups)
  C. Group Children  – isDefault (childRef metadata inside productGroups;
     no isRecipe on childRefs)
"""
from core.traversal import all_products


def _ref_id(ref: str) -> str:
    return ref.split(".", 1)[1] if "." in ref else ref


def run(prod: dict, uat: dict) -> dict:

    # ---- A. Products – isRecipe & isDefault ----
    def build_product_idx(parsed):
        idx = {}
        for dn, p in all_products(parsed).items():
            if dn not in idx:
                idx[dn] = {
                    "id":           p["key"],
                    "display_name": p["display_name"],
                    "is_recipe":    p["is_recipe"],
                    "is_default":   p.get("is_default", False),
                }
        return idx

    prod_p_idx = build_product_idx(prod)
    uat_p_idx  = build_product_idx(uat)
    p_findings = []

    for dn in sorted(set(prod_p_idx) | set(uat_p_idx)):
        p = prod_p_idx.get(dn)
        u = uat_p_idx.get(dn)
        name = (p or u)["display_name"]
        pid  = (p or u)["id"]
        if p is None:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": "N/A",          "uat_isRecipe":  u["is_recipe"],
                   "prod_isDefault": "N/A",         "uat_isDefault": u["is_default"],
                   "status": "NEW IN UAT"}
        elif u is None:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": p["is_recipe"],  "uat_isRecipe":  "N/A",
                   "prod_isDefault": p["is_default"], "uat_isDefault": "N/A",
                   "status": "MISSING IN UAT"}
        else:
            mismatch = (p["is_recipe"] != u["is_recipe"]) or (p["is_default"] != u["is_default"])
            status = "MISMATCH" if mismatch else "MATCH"
            row = {"id": pid, "name": name,
                   "prod_isRecipe": p["is_recipe"],  "uat_isRecipe":  u["is_recipe"],
                   "prod_isDefault": p["is_default"], "uat_isDefault": u["is_default"],
                   "status": status}
        p_findings.append(row)

    # ---- B. Modifier Groups – isRecipe ----
    def build_group_recipe_idx(parsed):
        idx = {}
        for key, g in (parsed.get("product_groups") or {}).items():
            dn = g["dn_key"]
            if dn not in idx:
                idx[dn] = {"id": g["key"], "display_name": g["display_name"], "is_recipe": g["is_recipe"]}
        return idx

    prod_g_idx = build_group_recipe_idx(prod)
    uat_g_idx  = build_group_recipe_idx(uat)
    g_findings = []

    for dn in sorted(set(prod_g_idx) | set(uat_g_idx)):
        p = prod_g_idx.get(dn)
        u = uat_g_idx.get(dn)
        name = (p or u)["display_name"]
        pid  = (p or u)["id"]
        if p is None:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": "N/A", "uat_isRecipe": u["is_recipe"], "status": "NEW IN UAT"}
        elif u is None:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": p["is_recipe"], "uat_isRecipe": "N/A", "status": "MISSING IN UAT"}
        elif p["is_recipe"] != u["is_recipe"]:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": p["is_recipe"], "uat_isRecipe": u["is_recipe"], "status": "MISMATCH"}
        else:
            row = {"id": pid, "name": name,
                   "prod_isRecipe": p["is_recipe"], "uat_isRecipe": u["is_recipe"], "status": "MATCH"}
        g_findings.append(row)

    # ---- C. Group Children – isDefault ----
    # isDefault is on the childRef entry inside productGroups, e.g.:
    # productGroups["options-xxx"].childRefs["products.grilled-onions-xxx"] = {"isDefault": true}

    def build_group_used_by_idx(parsed):
        """Returns {group_key: [parent product display names]} for all productGroups."""
        prods  = parsed.get("products", {})
        result = {}
        for pid, p in prods.items():
            p_name = p.get("display_name", pid)
            all_refs = list(p.get("ingredient_refs") or set()) + list(p.get("modifier_group_refs") or set())
            for ref in all_refs:
                grp_key = _ref_id(ref)
                lst = result.setdefault(grp_key, [])
                if p_name not in lst:
                    lst.append(p_name)
        return result

    def build_child_default_idx(parsed, group_used_by):
        prods = parsed.get("products", {})
        idx   = {}
        for key, g in (parsed.get("product_groups") or {}).items():
            g_dn   = g["dn_key"]
            g_name = g["display_name"]
            parents = group_used_by.get(key, [])
            used_by_product = ", ".join(sorted(parents)) if parents else "—"
            for child_ref, child_meta in (g.get("child_refs") or {}).items():
                if not child_ref.startswith("products."):
                    continue
                child_id   = _ref_id(child_ref)
                child_prod = prods.get(child_id)
                if not child_prod:
                    continue
                child_dn   = child_prod["dn_key"]
                child_name = child_prod["display_name"]
                is_default = bool((child_meta or {}).get("isDefault", False))
                combo = f"{g_dn}||{child_dn}"
                if combo not in idx:
                    idx[combo] = {
                        "id":              f"{key} › {child_id}",
                        "group_name":      g_name,
                        "child_name":      child_name,
                        "is_default":      is_default,
                        "used_by_product": used_by_product,
                    }
        return idx

    prod_g_used_by = build_group_used_by_idx(prod)
    uat_g_used_by  = build_group_used_by_idx(uat)
    prod_cd_idx = build_child_default_idx(prod, prod_g_used_by)
    uat_cd_idx  = build_child_default_idx(uat, uat_g_used_by)
    cd_findings = []

    for combo in sorted(set(prod_cd_idx) | set(uat_cd_idx)):
        p = prod_cd_idx.get(combo)
        u = uat_cd_idx.get(combo)
        entry = p or u
        label          = f"{entry['group_name']} › {entry['child_name']}"
        pid            = entry["id"]
        used_by_product = entry["used_by_product"]
        if p is None:
            row = {"id": pid, "name": label, "used_by_product": used_by_product,
                   "prod_isDefault": "N/A", "uat_isDefault": u["is_default"], "status": "NEW IN UAT"}
        elif u is None:
            row = {"id": pid, "name": label, "used_by_product": used_by_product,
                   "prod_isDefault": p["is_default"], "uat_isDefault": "N/A", "status": "MISSING IN UAT"}
        elif p["is_default"] != u["is_default"]:
            row = {"id": pid, "name": label, "used_by_product": used_by_product,
                   "prod_isDefault": p["is_default"], "uat_isDefault": u["is_default"], "status": "MISMATCH"}
        else:
            row = {"id": pid, "name": label, "used_by_product": used_by_product,
                   "prod_isDefault": p["is_default"], "uat_isDefault": u["is_default"], "status": "MATCH"}
        cd_findings.append(row)

    p_issues  = sum(1 for f in p_findings  if f["status"] == "MISMATCH")
    g_issues  = sum(1 for f in g_findings  if f["status"] == "MISMATCH")
    cd_issues = sum(1 for f in cd_findings if f["status"] == "MISMATCH")
    total_issues = p_issues + g_issues + cd_issues

    sub_checks = [
        {"subtitle": "A. Products – isRecipe & isDefault",
         "findings": p_findings,  "total": len(p_findings),  "issues": p_issues},
        {"subtitle": "B. Modifier Groups – isRecipe",
         "findings": g_findings,  "total": len(g_findings),  "issues": g_issues},
        {"subtitle": "C. Group Children – isDefault",
         "findings": cd_findings, "total": len(cd_findings), "issues": cd_issues},
    ]

    # Flat findings for Excel export (add object_type column for context)
    flat_findings = (
        [dict(object_type="Product",        **f) for f in p_findings]  +
        [dict(object_type="Modifier Group", **f) for f in g_findings]  +
        [dict(object_type="Group Child",    **f) for f in cd_findings]
    )

    return {
        "title":      "isRecipe/Default Flag Mismatches",
        "sub_checks": sub_checks,
        "findings":   flat_findings,
        "issues":     total_issues,
        "total":      len(flat_findings),
    }

