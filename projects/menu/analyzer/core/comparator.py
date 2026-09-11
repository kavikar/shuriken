"""
Comparator: Orchestrates all 8 checks and returns a unified results dict.
"""
from datetime import datetime

from checks import (
    product_count,
    ingredients,
    recipe_flags,
    modifier_minmax,
    display_names,
    modifier_ordering,
    delta_products,
    non_virtual,
)


def compare(prod_parsed: dict, uat_parsed: dict, meta: dict) -> dict:
    """
    Run all 8 checks and return a unified results structure.
    meta = { brand, prod_store, uat_store, prod_url, uat_url }
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    checks_result = {
        "product_count":      product_count.run(prod_parsed, uat_parsed),
        "ingredients":        ingredients.run(prod_parsed, uat_parsed),
        "recipe_flags":       recipe_flags.run(prod_parsed, uat_parsed),
        "modifier_minmax":    modifier_minmax.run(prod_parsed, uat_parsed),
        "display_names":      display_names.run(prod_parsed, uat_parsed),
        "modifier_ordering":  modifier_ordering.run(prod_parsed, uat_parsed),
        "delta_products":     delta_products.run(prod_parsed, uat_parsed),
        "non_virtual":        non_virtual.run(prod_parsed, uat_parsed),
    }

    total_issues = sum(v["issues"] for v in checks_result.values())
    critical = checks_result["non_virtual"].get("critical", 0)
    warnings = checks_result["non_virtual"].get("warnings", 0)

    return {
        "meta": {
            **meta,
            "timestamp": timestamp,
            "prod_menu_name": prod_parsed["meta"].get("displayName", ""),
            "uat_menu_name": uat_parsed["meta"].get("displayName", ""),
            "prod_product_count": len(prod_parsed.get("products", {})),
            "uat_product_count": len(uat_parsed.get("products", {})),
            "prod_group_count": len(prod_parsed.get("product_groups", {})),
            "uat_group_count": len(uat_parsed.get("product_groups", {})),
            "prod_category_count": len(prod_parsed.get("categories", {})),
            "uat_category_count": len(uat_parsed.get("categories", {})),
        },
        "summary": {
            "total_issues": total_issues,
            "critical": critical,
            "warnings": warnings,
            "new_products": checks_result["delta_products"].get("new_count", 0),
            "removed_products": checks_result["delta_products"].get("removed_count", 0),
        },
        "checks": checks_result,
    }
