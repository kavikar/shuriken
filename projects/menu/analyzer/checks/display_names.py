"""
Check 5 – Display Name & Description Changes

Produces ONE row per logical product (norm_key group) to avoid noise from
environment-specific UUID suffixes. Within each norm_key group, an exact
key match is preferred so the right UAT variant is compared against PROD.

Example: honey-bbq-sauce-7e2b4dd8 (PROD, has description) vs the UAT pool
[honey-bbq-sauce-7e2b4dd8, honey-bbq-sauce-3d27c899] → picks the exact-key
match (7e2b4dd8↔7e2b4dd8) rather than the wrong variant (3d27c899).
"""
import re


def _norm_key(k: str) -> str:
    return re.sub(r'-[0-9a-f]{8}$', '', k)


def run(prod: dict, uat: dict) -> dict:
    prod_by_key = prod.get("products", {})
    uat_by_key  = uat.get("products",  {})

    # Group products by norm_key
    prod_nk: dict = {}
    for key, p in prod_by_key.items():
        prod_nk.setdefault(_norm_key(key), []).append(p)

    uat_nk: dict = {}
    for key, p in uat_by_key.items():
        uat_nk.setdefault(_norm_key(key), []).append(p)

    pairs = []
    for nk in sorted(set(prod_nk) & set(uat_nk)):
        pp_list = prod_nk[nk]
        uu_list = uat_nk[nk]

        # Prefer exact key match (same full ID in both envs)
        uat_key_idx = {p["key"]: p for p in uu_list}
        chosen = None
        for pp in pp_list:
            if pp["key"] in uat_key_idx:
                chosen = (pp, uat_key_idx[pp["key"]])
                break

        # Fallback: first of each (different-hash env promotion)
        if chosen is None:
            chosen = (pp_list[0], uu_list[0])

        pairs.append(chosen)

    findings = []

    for p, u in pairs:

        p_dn = p.get("display_name", "")
        u_dn = u.get("display_name", "")
        p_desc = p.get("description", "") or ""
        u_desc = u.get("description", "") or ""

        dn_changed = p_dn.strip() != u_dn.strip()
        desc_changed = p_desc.strip() != u_desc.strip()

        if dn_changed or desc_changed:
            status_parts = []
            if dn_changed:
                status_parts.append("Name Changed")
            if desc_changed:
                status_parts.append("Desc Changed")
            findings.append({
                "prod_id": p["key"],
                "uat_id":  u["key"],
                "prod_display_name": p_dn,
                "uat_display_name": u_dn,
                "prod_description": p_desc[:120] or "—",
                "uat_description": u_desc[:120] or "—",
                "status": " | ".join(status_parts),
            })
        else:
            findings.append({
                "prod_id": p["key"],
                "uat_id":  u["key"],
                "prod_display_name": p_dn,
                "uat_display_name": u_dn,
                "prod_description": p_desc[:120] or "—",
                "uat_description": u_desc[:120] or "—",
                "status": "MATCH",
            })

    issues = sum(1 for f in findings if f["status"] != "MATCH")
    return {
        "title": "Display Name & Description Changes",
        "columns": ["PROD ID", "UAT ID", "PROD Display Name", "UAT Display Name",
                    "PROD Description", "UAT Description", "Status"],
        "findings": findings,
        "issues": issues,
        "total": len(findings),
    }
