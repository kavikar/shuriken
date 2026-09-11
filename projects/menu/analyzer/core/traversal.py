"""
core/traversal.py – Shared deep-traversal helper

Collects ALL reachable products from a parsed menu by following every
reference path the API supports:

  1. Direct top-level products
  2. alternatives{}
  3. ingredientRefs{} → productGroups → childRefs → products
  4. modifierGroupRefs{} → productGroups → childRefs → products
  5. relatedProducts{}
  6. customAttributes.coreProduct  (already stored as `core_product` field)
"""


def _ref_id(ref: str) -> str:
    return ref.split(".", 1)[1] if "." in ref else ref


def all_products(parsed: dict) -> dict:
    """
    Return a dict  { dn_key -> product_entry }  covering every product
    reachable via all 6 traversal paths.

    When the same dn_key appears multiple times (e.g. same product in
    multiple modifier groups), the first encountered entry wins so callers
    get one representative record per logical product.
    """
    prods  = parsed.get("products", {})
    groups = parsed.get("product_groups", {})
    idx: dict = {}

    def _add(p: dict):
        dn = p["dn_key"]
        if dn not in idx:
            idx[dn] = p

    def _group_children(ref_set):
        for ref in ref_set:
            grp = groups.get(_ref_id(ref))
            if not grp:
                continue
            for child_ref in (grp.get("child_refs") or {}).keys():
                if child_ref.startswith("products."):
                    child = prods.get(_ref_id(child_ref))
                    if child:
                        yield child

    for key, p in prods.items():
        # 1. Direct product
        _add(p)

        # 2. alternatives
        for ref in p.get("alternatives", set()):
            alt = prods.get(_ref_id(ref))
            if alt:
                _add(alt)

        # 3. ingredientRefs → productGroups → childRefs
        for child in _group_children(p.get("ingredient_refs", set())):
            _add(child)

        # 4. modifierGroupRefs → productGroups → childRefs
        for child in _group_children(p.get("modifier_group_refs", set())):
            _add(child)

        # 5. relatedProducts
        for ref in p.get("related_products", set()):
            rel = prods.get(_ref_id(ref))
            if rel:
                _add(rel)

        # 6. coreProduct — already normalised as `core_product` key in parser;
        #    find any product whose dn_key matches the core_product value
        core = p.get("core_product", "")
        if core and core != p["dn_key"]:
            core_p = next(
                (v for v in prods.values() if v["dn_key"] == core), None
            )
            if core_p:
                _add(core_p)

    return idx
