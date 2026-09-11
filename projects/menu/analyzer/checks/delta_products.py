"""
Check 7 – Delta Product Report
Identifies products present in UAT but not PROD (new items) and vice versa.
Covers all reachable products: top-level, alternatives, ingredientRefs,
modifierGroupRefs, relatedProducts, coreProduct.
"""
from collections import defaultdict
from core.traversal import all_products


def _get_product_category(product_key: str, data: dict) -> str:
    """Walk categories to find which one directly references this product."""
    ref = f"products.{product_key}"
    for cat in (data.get("categories") or {}).values():
        if ref in (cat.get("child_refs") or cat.get("childRefs") or {}):
            return cat.get("display_name") or cat.get("displayName", "Unknown")
    return "Uncategorised"


def _get_product_category_from_parsed(product_key: str, parsed: dict) -> str:
    ref = f"products.{product_key}"
    for cat in parsed.get("categories", {}).values():
        if ref in (cat.get("child_refs") or {}):
            return cat.get("display_name", "Uncategorised")
    return "Uncategorised"


def run(prod: dict, uat: dict) -> dict:
    prod_all = all_products(prod)
    uat_all  = all_products(uat)

    prod_norm_keys = defaultdict(list)
    for p in prod_all.values():
        prod_norm_keys[p["norm_key"]].append(p)

    uat_norm_keys = defaultdict(list)
    for p in uat_all.values():
        uat_norm_keys[p["norm_key"]].append(p)

    findings = []

    # Products in UAT but NOT in PROD (new items)
    for dn, u in uat_all.items():
        if dn not in prod_all:
            nk_match = bool(prod_norm_keys.get(u["norm_key"]))
            if not nk_match:
                cat = _get_product_category_from_parsed(u["key"], uat)
                findings.append({
                    "product": u["display_name"],
                    "product_id": "products." + u["key"],
                    "category": cat,
                    "is_virtual": u.get("is_virtual", False),
                    "is_recipe": u.get("is_recipe", False),
                    "price": u.get("price"),
                    "calories": u.get("total_calories"),
                    "status": "NEW IN UAT",
                    "test_action": "Requires new test case",
                })

    # Products in PROD but NOT in UAT (removed items)
    for dn, p in prod_all.items():
        if dn not in uat_all:
            nk_match = bool(uat_norm_keys.get(p["norm_key"]))
            if not nk_match:
                cat = _get_product_category_from_parsed(p["key"], prod)
                findings.append({
                    "product": p["display_name"],
                    "product_id": "products." + p["key"],
                    "category": cat,
                    "is_virtual": p.get("is_virtual", False),
                    "is_recipe": p.get("is_recipe", False),
                    "price": p.get("price"),
                    "calories": p.get("total_calories"),
                    "status": "REMOVED FROM UAT",
                    "test_action": "Verify removal is intentional; deprecate test cases",
                })

    # Sort: new first, then removed
    findings.sort(key=lambda x: (0 if x["status"] == "NEW IN UAT" else 1, x["category"], x["product"]))

    new_count = sum(1 for f in findings if f["status"] == "NEW IN UAT")
    removed_count = sum(1 for f in findings if f["status"] == "REMOVED FROM UAT")

    return {
        "title": "Delta Product Report",
        "columns": ["Product", "Norm Key", "Category", "Is Virtual", "Is Recipe",
                    "Price", "Calories", "Status", "Test Action Required"],
        "findings": findings,
        "issues": len(findings),
        "new_count": new_count,
        "removed_count": removed_count,
        "total": len(findings),
    }
