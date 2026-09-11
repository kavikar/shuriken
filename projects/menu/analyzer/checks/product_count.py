"""
Check 1 – Product Counts by Category
Compares the number of products in each named category between PROD and UAT.
"""


def run(prod: dict, uat: dict) -> dict:
    prod_counts = prod.get("cat_counts", {})
    uat_counts = uat.get("cat_counts", {})

    all_keys = set(prod_counts) | set(uat_counts)
    all_cats = sorted(all_keys, key=lambda k: (0 if k.upper() == "MAIN" else 1, k))
    findings = []

    for cat_name in all_cats:
        p = prod_counts.get(cat_name)
        u = uat_counts.get(cat_name)
        p_count = p["count"] if p else 0
        u_count = u["count"] if u else 0

        p_cat_id = ("categories." + p["cat_id"]) if p and p.get("cat_id") else ""
        u_cat_id = ("categories." + u["cat_id"]) if u and u.get("cat_id") else ""
        if p_count != u_count:
            status = "MISSING IN UAT" if u is None else ("MISSING IN PROD" if p is None else "COUNT MISMATCH")
            findings.append({
                "category": (p or u or {}).get("display_name", cat_name),
                "prod_cat_id": p_cat_id,
                "uat_cat_id": u_cat_id,
                "prod_count": p_count,
                "uat_count": u_count,
                "delta": u_count - p_count,
                "status": status,
            })
        else:
            findings.append({
                "category": (p or u or {}).get("display_name", cat_name),
                "prod_cat_id": p_cat_id,
                "uat_cat_id": u_cat_id,
                "prod_count": p_count,
                "uat_count": u_count,
                "delta": 0,
                "status": "MATCH",
            })

    issues = sum(1 for f in findings if f["status"] != "MATCH")
    return {
        "title": "Product Counts by Category",
        "columns": ["Category", "PROD Count", "UAT Count", "Delta", "Status"],
        "findings": findings,
        "issues": issues,
        "total": len(findings),
    }
