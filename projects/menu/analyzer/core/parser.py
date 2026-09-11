"""
Parser: Normalizes raw IDP menu JSON into an indexed, comparison-ready structure.

Key design choices:
- Products are indexed by:
    1) Exact key (e.g. 'bun-39b63ffb')
    2) Normalized key – trailing 8-char hex hash stripped (e.g. 'bun')
    3) Display-name key – uppercase trimmed name
    4) coreProduct from customAttributes (most reliable cross-env identifier)
- ProductGroups (modifier groups) indexed by displayName key.
- Categories indexed by displayName key.
"""

import re
from collections import defaultdict
from typing import Dict, Any, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm_key(key: str) -> str:
    """Strip trailing 8-char hex hash.  'bun-39b63ffb' -> 'bun'"""
    return re.sub(r"-[0-9a-f]{8}$", "", key)


def _dn_key(name: str) -> str:
    """Normalise display name for matching: uppercase stripped."""
    return (name or "").strip().upper()


def _ref_id(ref: str) -> str:
    """'products.bun-39b63ffb' -> 'bun-39b63ffb'"""
    return ref.split(".", 1)[1] if "." in ref else ref


def _get_calories(prod: dict) -> Optional[float]:
    nutrition = prod.get("nutrition") or {}
    return nutrition.get("totalCalories")


# ---------------------------------------------------------------------------
# Category tree walker
# ---------------------------------------------------------------------------

def _build_category_product_map(data: dict) -> Dict[str, List[str]]:
    """
    Walk the full category tree from rootCategoryRef.
    Returns {category_display_name -> [product_keys_directly_in_this_cat]}
    """
    categories = data.get("categories", {}) or {}
    products = data.get("products", {}) or {}
    root_ref = data.get("rootCategoryRef", "")
    root_id = _ref_id(root_ref) if root_ref else None

    cat_direct_products: Dict[str, List[str]] = defaultdict(list)

    visited = set()

    def walk(cat_id: str):
        if cat_id in visited:
            return
        visited.add(cat_id)
        cat = categories.get(cat_id, {})
        dn = _dn_key(cat.get("displayName", cat_id))
        for child_ref in (cat.get("childRefs") or {}).keys():
            if child_ref.startswith("products."):
                pid = _ref_id(child_ref)
                cat_direct_products[dn].append(pid)
            elif child_ref.startswith("categories."):
                walk(_ref_id(child_ref))

    if root_id:
        walk(root_id)
    # Catch any orphan categories
    for cat_id in categories:
        walk(cat_id)

    return dict(cat_direct_products)


def _build_product_category_map(data: dict) -> Dict[str, List[str]]:
    """
    Three-tier approach to map every product to its parent category names:

    Tier 1 – category.childRefs walk: direct product children of any category.
    Tier 2 – product.groupIds with 'categories.xxx': many B2 products carry
              their category membership here (virtual/orderable items).
    Tier 3 – productGroups siblings: size-variant products that only have
              'productGroups.xxx' in groupIds get their category inferred from
              the productGroup's other siblings that have tier-1/2 categories.
    """
    categories = data.get("categories", {}) or {}
    raw_prods  = data.get("products", {})   or {}
    raw_groups = data.get("productGroups", {}) or {}

    result: Dict[str, set] = {}

    # ── Tier 1: category.childRefs ────────────────────────────────────────
    visited: set = set()
    root_ref = data.get("rootCategoryRef", "")
    root_id  = _ref_id(root_ref) if root_ref else None

    def walk(cat_id: str):
        if cat_id in visited:
            return
        visited.add(cat_id)
        cat      = categories.get(cat_id, {})
        cat_name = (cat.get("displayName") or "").strip()
        for child_ref in (cat.get("childRefs") or {}).keys():
            if child_ref.startswith("products."):
                pid = _ref_id(child_ref)
                p   = raw_prods.get(pid)
                if p and cat_name:
                    nk = _norm_key(pid)
                    dn_k = _dn_key(p.get("displayName", ""))
                    result.setdefault(pid,  set()).add(cat_name)   # full key
                    result.setdefault(nk,   set()).add(cat_name)   # norm key
                    result.setdefault(dn_k, set()).add(cat_name)   # display name key
            elif child_ref.startswith("categories."):
                walk(_ref_id(child_ref))

    if root_id:
        walk(root_id)
    for cat_id in categories:
        walk(cat_id)

    # ── Tier 2: product.groupIds with 'categories.xxx' ────────────────────
    for pid, p in raw_prods.items():
        dn = _dn_key(p.get("displayName", ""))
        nk = _norm_key(pid)
        if not dn:
            continue
        for gref in (p.get("groupIds") or []):
            if gref.startswith("categories."):
                cat_id = _ref_id(gref)
                cat    = categories.get(cat_id, {})
                cat_name = (cat.get("displayName") or "").strip()
                if cat_name:
                    result.setdefault(dn, set()).add(cat_name)
                    result.setdefault(nk, set()).add(cat_name)
                    result.setdefault(pid, set()).add(cat_name)   # full key

    # ── Tier 3: productGroups siblings fallback ───────────────────────────
    # Build group_id → [norm_keys of members] map from groupIds
    group_members: Dict[str, List[str]] = {}
    for pid, p in raw_prods.items():
        nk = _norm_key(pid)
        for gref in (p.get("groupIds") or []):
            if gref.startswith("productGroups."):
                gid = _ref_id(gref)
                group_members.setdefault(gid, []).append(nk)

    # For products still not found, inherit cats from siblings
    for pid, p in raw_prods.items():
        nk = _norm_key(pid)
        dn = _dn_key(p.get("displayName", ""))
        if not nk or nk in result:
            continue
        for gref in (p.get("groupIds") or []):
            if gref.startswith("productGroups."):
                gid = _ref_id(gref)
                for sibling_nk in group_members.get(gid, []):
                    if sibling_nk in result:
                        result.setdefault(nk,  set()).update(result[sibling_nk])
                        result.setdefault(dn,  set()).update(result[sibling_nk])
                        result.setdefault(pid, set()).update(result[sibling_nk])
                # Also check productGroup childRefs for siblings with category refs
                grp = raw_groups.get(gid, {})
                for cref in (grp.get("childRefs") or {}).keys():
                    if cref.startswith("products."):
                        sib_pid = _ref_id(cref)
                        sib_nk  = _norm_key(sib_pid)
                        if sib_nk in result:
                            result.setdefault(nk,  set()).update(result[sib_nk])
                            result.setdefault(dn,  set()).update(result[sib_nk])
                            result.setdefault(pid, set()).update(result[sib_nk])
                        if sib_pid in result:
                            result.setdefault(pid, set()).update(result[sib_pid])

    return {k: sorted(v) for k, v in result.items()}


def _build_category_recursive_counts(data: dict) -> Dict[str, int]:
    """
    Returns {category_display_name -> total recursive product count}
    """
    categories = data.get("categories", {}) or {}
    visited_global = set()

    def collect(cat_id: str, local_visited: set) -> List[str]:
        if cat_id in local_visited:
            return []
        local_visited.add(cat_id)
        cat = categories.get(cat_id, {})
        prods = []
        for child_ref in (cat.get("childRefs") or {}).keys():
            if child_ref.startswith("products."):
                prods.append(_ref_id(child_ref))
            elif child_ref.startswith("categories."):
                prods.extend(collect(_ref_id(child_ref), local_visited))
        return prods

    result = {}
    for cat_id, cat in categories.items():
        dn = _dn_key(cat.get("displayName", cat_id))
        prods = collect(cat_id, set())
        if prods:
            if dn not in result:
                result[dn] = {"count": 0, "products": [], "cat_id": cat_id}
            if result[dn]["count"] < len(prods):
                result[dn] = {
                    "count": len(prods),
                    "products": prods,
                    "cat_id": cat_id,
                    "display_name": cat.get("displayName", cat_id),
                }
    return result


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_menu(data: dict) -> dict:
    """
    Parse raw IDP menu JSON into a normalised, indexed structure ready for
    comparison.
    """
    raw_products        = data.get("products", {})        or {}
    raw_groups          = data.get("productGroups", {})   or {}
    raw_categories      = data.get("categories", {})      or {}
    raw_modifier_groups = data.get("modifierGroups", {})  or {}

    # ---- Products ----
    products: Dict[str, dict] = {}
    products_by_name: Dict[str, List[str]] = defaultdict(list)
    products_by_norm_key: Dict[str, List[str]] = defaultdict(list)

    for key, prod in raw_products.items():
        nk = _norm_key(key)
        dn = prod.get("displayName", "")
        dn_k = _dn_key(dn)
        core = (_dn_key((prod.get("customAttributes") or {}).get("coreProduct", ""))
                or dn_k)

        entry = {
            "key": key,
            "norm_key": nk,
            "display_name": dn,
            "dn_key": dn_k,
            "core_product": core,
            "description": prod.get("description", ""),
            "is_available": prod.get("isAvailable"),
            "is_virtual": prod.get("isVirtual", False),
            "is_recipe": prod.get("isRecipe", False),
            "is_default": prod.get("isDefault", False),
            "price": prod.get("price"),
            "total_calories": _get_calories(prod),
            "group_ids": prod.get("groupIds") or [],
            "image_url": prod.get("imageUrl", ""),
            "custom_attributes": prod.get("customAttributes") or {},
            "quantity": prod.get("quantity") or {},
            "ingredient_refs":    set((prod.get("ingredientRefs")    or {}).keys()),
            "modifier_group_refs": set((prod.get("modifierGroupRefs") or {}).keys()),
            "alternatives":        set((prod.get("alternatives")       or {}).keys()),
            "related_products":    set((prod.get("relatedProducts")    or {}).keys()),
            "alt_group_refs":      set(((prod.get("relatedProducts") or {}).get("alternatives") or {}).keys()),
            "ingredients": prod.get("ingredients") or [],
            # Ordered lists for sequencing check (insertion-order preserved)
            "ingredient_refs_ordered":   list((prod.get("ingredientRefs")    or {}).keys()),
            "ingredient_group_names": [
                _dn_key(raw_groups.get(_ref_id(r), {}).get("displayName", ""))
                or _norm_key(_ref_id(r))
                for r in (prod.get("ingredientRefs") or {}).keys()
            ],
            "modifier_group_refs_ordered": list((prod.get("modifierGroupRefs") or {}).keys()),
            "modifier_group_names": [
                _dn_key(raw_modifier_groups.get(_ref_id(r), {}).get("displayName", ""))
                or _norm_key(_ref_id(r))
                for r in (prod.get("modifierGroupRefs") or {}).keys()
            ],
        }
        products[key] = entry
        products_by_name[dn_k].append(key)
        products_by_norm_key[nk].append(key)

    # ---- ProductGroups (modifier groups) ----
    product_groups: Dict[str, dict] = {}
    groups_by_name: Dict[str, List[str]] = defaultdict(list)

    for key, grp in raw_groups.items():
        nk = _norm_key(key)
        dn = grp.get("displayName", "")
        dn_k = _dn_key(dn)
        child_refs = grp.get("childRefs") or {}
        sel_qty = grp.get("selectionQuantity") or {}

        entry = {
            "key": key,
            "norm_key": nk,
            "display_name": dn,
            "dn_key": dn_k,
            "is_recipe": grp.get("isRecipe", False),
            "entree_selection": grp.get("entreeSelection", False),
            "min": sel_qty.get("min"),
            "max": sel_qty.get("max"),
            "child_refs": child_refs,
            "child_order": list(child_refs.keys()),
            "child_count": len(child_refs),
            # Normalised child names for order comparison
            "child_norm_names": [
                _norm_key(_ref_id(r)) for r in child_refs.keys()
            ],
            # Display-name keys for order comparison (more human-readable)
            "child_display_names": [
                _dn_key(raw_products.get(_ref_id(r), {}).get("displayName", ""))
                or _norm_key(_ref_id(r))
                for r in child_refs.keys()
            ],
        }
        product_groups[key] = entry
        groups_by_name[dn_k].append(key)

    # ---- Categories ----
    categories: Dict[str, dict] = {}
    categories_by_name: Dict[str, List[str]] = defaultdict(list)

    for key, cat in raw_categories.items():
        nk = _norm_key(key)
        dn = cat.get("displayName", "")
        dn_k = _dn_key(dn)
        child_refs = cat.get("childRefs") or {}
        product_children = [r for r in child_refs if r.startswith("products.")]
        category_children = [r for r in child_refs if r.startswith("categories.")]

        # Ordered display-name keys for products/sub-categories (sequencing check)
        product_children_dn_keys = [
            _dn_key(raw_products.get(_ref_id(r), {}).get("displayName", _ref_id(r)))
            for r in child_refs.keys()
            if r.startswith("products.")
        ]
        category_children_dn_keys = [
            _dn_key(raw_categories.get(_ref_id(r), {}).get("displayName", _ref_id(r)))
            for r in child_refs.keys()
            if r.startswith("categories.")
        ]

        entry = {
            "key": key,
            "norm_key": nk,
            "display_name": dn,
            "dn_key": dn_k,
            "is_available": cat.get("isAvailable", True),
            "child_refs": child_refs,
            "product_count": len(product_children),
            "product_children": product_children,
            "category_children": category_children,
            "product_children_dn_keys":  product_children_dn_keys,
            "category_children_dn_keys": category_children_dn_keys,
        }
        categories[key] = entry
        categories_by_name[dn_k].append(key)

    # ---- ModifierGroups (wing-type, sauce-preference, etc.) ----
    modifier_groups: Dict[str, dict] = {}
    modifier_groups_by_name: Dict[str, List[str]] = defaultdict(list)

    for key, mg in raw_modifier_groups.items():
        nk = _norm_key(key)
        dn = mg.get("displayName", "")
        dn_k = _dn_key(dn)
        child_refs = mg.get("childRefs") or {}
        sel_qty = mg.get("selectionQuantity") or {}

        entry = {
            "key": key,
            "norm_key": nk,
            "display_name": dn,
            "dn_key": dn_k,
            "min": sel_qty.get("min"),
            "max": sel_qty.get("max"),
            "child_refs": child_refs,
            "child_count": len(child_refs),
            "child_order": list(child_refs.keys()),
            # Norm-keys for ID display
            "child_norm_names": [
                _norm_key(_ref_id(r)) for r in child_refs.keys()
            ],
            # Resolved display-name sequence for ordering check
            "child_display_names": [
                _dn_key(raw_products.get(_ref_id(r), {}).get("displayName", ""))
                or _norm_key(_ref_id(r))
                for r in child_refs.keys()
            ],
        }
        modifier_groups[key] = entry
        modifier_groups_by_name[dn_k].append(key)

    # ---- Category recursive counts ----
    cat_counts = _build_category_recursive_counts(data)

    # ---- Product → category map ----
    product_to_cats = _build_product_category_map(data)

    return {
        "meta": {
            "displayName": data.get("displayName", ""),
            "posMenuId": data.get("posMenuId", ""),
            "is_available": data.get("isAvailable", True),
            "root_category_ref": data.get("rootCategoryRef", ""),
        },
        "products": products,
        "product_groups": product_groups,
        "modifier_groups": modifier_groups,
        "categories": categories,
        # Lookup indices
        "products_by_name": dict(products_by_name),
        "products_by_norm_key": dict(products_by_norm_key),
        "groups_by_name": dict(groups_by_name),
        "modifier_groups_by_name": dict(modifier_groups_by_name),
        "categories_by_name": dict(categories_by_name),
        # Category → recursive product counts
        "cat_counts": cat_counts,
        # Product → immediate-parent category display names
        "product_to_cats": product_to_cats,
    }
