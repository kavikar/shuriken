# -*- coding: utf-8 -*-
"""
Multi-Brand Menu Mapping Validator — Single-File Application
============================================================
Validates product POS-ID mappings between Location Menu and Master Menu,
and compares UAT vs PROD master menus for delta analysis.

Supports: B1 (Brand One) · B2 (Brand Two)

Sections
--------
  1. Imports & Setup
  2. Brand Configuration
  3. Validator Engine       (Location vs Master product mapping)
  4. Master Delta Engine    (UAT Master vs PROD Master comparison)
  5. Flask API Server       (REST endpoints + dashboard)
"""

# ══════════════════════════════════════════════════════════════════════════════
# 1. IMPORTS & SETUP
# ══════════════════════════════════════════════════════════════════════════════

import json
import os
import re
import sys
import glob
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests as http_requests
import urllib3
from flask import Flask, jsonify, send_from_directory, request, redirect, make_response
from flask_cors import CORS
from urllib.parse import urlparse, parse_qs

# Corporate-proxy escape hatch: TLS verification is on by default and only
# disabled when explicitly opted into, rather than always skipped.
_INSECURE_TLS = os.environ.get("ALLOW_INSECURE_TLS") == "1"
if _INSECURE_TLS:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OUTPUT_ROOT = 'Reports'
os.makedirs(OUTPUT_ROOT, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# 2. BRAND CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BrandConfig:
    """Configuration for a single brand."""
    brand_code: str
    brand_name: str
    brand_emoji: str

    # MenuApi API
    api_base_url: str
    api_auth_token: str
    master_location_id: str
    sample_location_id: str

    # Theme colours (CSS)
    primary_color: str
    primary_dark: str
    gradient_start: str
    gradient_end: str

    # Mapping fields
    primary_mapping_field: str
    logo_url: str = ''
    extra_mapping_fields: List[str] = field(default_factory=list)

    # Category inference
    category_keywords: Dict[str, List[str]] = field(default_factory=dict)

    # Local fallback file paths
    default_location_file: Optional[str] = None
    default_master_file: Optional[str] = None

    # Sample cURL commands
    sample_curl_location: str = ''
    sample_curl_master: str = ''

    # Master Delta tokens/cookies
    uat_master_token: str = ''
    prod_master_token: str = ''
    uat_master_cookie: str = ''
    prod_master_cookie: str = ''
    sample_curl_delta_uat: str = ''
    sample_curl_delta_prod: str = ''


# ── B1 (Brand One) ──────────────────────────────────────────────────────────────
B1_CONFIG = BrandConfig(
    brand_code='B1',
    brand_name="Brand One",
    brand_emoji='🍔',
    logo_url='https://www.google.com/s2/favicons?domain=brand1.example&sz=128',

    api_base_url='https://menu-api.example/api/v1/menu_events/data',
    api_auth_token='REPLACE_ME_TOKEN',
    master_location_id='master',
    sample_location_id='1000',

    primary_color='#4a6480',
    primary_dark='#2d3f52',
    gradient_start='#4a6480',
    gradient_end='#2d3f52',

    primary_mapping_field='posId',
    extra_mapping_fields=[
        'menuItemId', 'optionGroupId',
        'drinkComponentId', 'entreeComponentId', 'sideComponentId',
    ],

    category_keywords={
        'Beverages': ['drink', 'tea', 'shake', 'lemonade', 'coffee', 'juice', 'water', 'slush', 'soda'],
        'Sides':     ['fries', 'cakes', 'bites', 'sticks', 'rings', 'mozzarella', 'jalapeno', 'onion'],
        'Entrees':   ['beef', 'chicken', 'turkey', 'gyro', 'wrap', 'sandwich', 'burger', 'roast', 'melt',
                      'sub', 'fish', 'pork'],
        'Condiments': ['sauce', 'dressing', 'ranch', 'ketchup', 'mayo', 'cheese', 'condiment'],
    },

    default_location_file='../B1_Master_Menu_Mapping/B1_Menu_UAT_IAC_Response_1000.txt',
    default_master_file='../B1_Master_Menu_Mapping/B1_Master_MENU_LLE.txt',

    sample_curl_location=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=1000&brand=B1&event_type=menu' \\\n"
        "--header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "--header 'Cookie: _session_id=REPLACE_ME; _session_id=REPLACE_ME'"
    ),
    sample_curl_master=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=master&brand=B1&event_type=menu' \\\n"
        "--header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "--header 'Cookie: _session_id=REPLACE_ME; _session_id=REPLACE_ME'"
    ),

    uat_master_token='REPLACE_ME_TOKEN',
    prod_master_token='REPLACE_ME_TOKEN',
    uat_master_cookie='_session_id=REPLACE_ME; _session_id=REPLACE_ME',
    prod_master_cookie='_session_id=REPLACE_ME; _session_id=REPLACE_ME',
    sample_curl_delta_uat=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=master&brand=B1&event_type=menu' \\\n"
        "  --header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "  --header 'Cookie: _session_id=REPLACE_ME; "
        "_session_id=REPLACE_ME'"
    ),
    sample_curl_delta_prod=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=master&brand=B1&event_type=menu' \\\n"
        "  --header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "  --header 'Cookie: _session_id=REPLACE_ME; "
        "_session_id=REPLACE_ME'"
    ),
)


# ── B2 (Brand Two) ──────────────────────────────────────────────────
B2_CONFIG = BrandConfig(
    brand_code='B2',
    brand_name='Brand Two',
    brand_emoji='🍗',
    logo_url='https://www.google.com/s2/favicons?domain=brand2.example&sz=128',

    api_base_url='https://menu-api.example/api/v1/menu_events/data',
    api_auth_token='REPLACE_ME_TOKEN',
    master_location_id='master',
    sample_location_id='5',

    primary_color='#0891b2',
    primary_dark='#0e7490',
    gradient_start='#0891b2',
    gradient_end='#164e63',

    primary_mapping_field='posId',
    extra_mapping_fields=[
        'salesItemId', 'optionGroupId', 'menuItemId',
    ],

    category_keywords={
        'Wings':      ['wing', 'boneless', 'traditional', 'smoked'],
        'Burgers':    ['burger', 'smash', 'patty', 'impossible'],
        'Sandwiches': ['sandwich', 'wrap', 'chicken sandwich', 'nashville'],
        'Sides':      ['fries', 'tots', 'rings', 'coleslaw', 'corn', 'side', 'chips',
                       'celery', 'carrot', 'wedge'],
        'Sauces':     ['sauce', 'dry rub', 'seasoning', 'glaze', 'garlic', 'parmesan', 'buffalo',
                       'bbq', 'mango', 'habanero', 'teriyaki', 'honey', 'lemon', 'pepper',
                       'blazin', 'hot'],
        'Beverages':  ['drink', 'tea', 'shake', 'lemonade', 'coffee', 'juice', 'water', 'soda',
                       'beer', 'wine', 'cocktail', 'margarita', 'daiquiri'],
        'Salads':     ['salad', 'garden', 'caesar'],
        'Appetizers': ['nacho', 'pretzel', 'queso', 'mozzarella', 'cheese curd', 'egg roll',
                       'popper', 'mushroom', 'pickle', 'sampler'],
        'Desserts':   ['dessert', 'brownie', 'cookie', 'sundae', 'cake', 'cheesecake'],
        'Kids':       ['kids', 'child'],
    },

    default_location_file='../B2_Master_Menu_Mapping/B2_NCR_Response.txt',
    default_master_file='../B2_Master_Menu_Mapping/B2_IAC_Master_Menu_LookUp.txt',

    sample_curl_location=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=5&brand=B2&event_type=menu' \\\n"
        "--header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "--header 'Cookie: _session_id=REPLACE_ME; _session_id=REPLACE_ME'"
    ),
    sample_curl_master=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=5&brand=B2&event_type=menu' \\\n"
        "--header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "--header 'Cookie: _session_id=REPLACE_ME; _session_id=REPLACE_ME'"
    ),

    uat_master_token='REPLACE_ME_TOKEN',
    prod_master_token='REPLACE_ME_TOKEN',
    uat_master_cookie='_session_id=REPLACE_ME; _session_id=REPLACE_ME',
    prod_master_cookie='_session_id=REPLACE_ME; _session_id=REPLACE_ME',
    sample_curl_delta_uat=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=master&brand=B2&event_type=menu' \\\n"
        "  --header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "  --header 'Cookie: _session_id=REPLACE_ME; "
        "_session_id=REPLACE_ME'"
    ),
    sample_curl_delta_prod=(
        "curl --location 'https://menu-api.example/api/v1/menu_events/data"
        "?location_id=master&brand=B2&event_type=menu' \\\n"
        "  --header 'Authorization: Bearer REPLACE_ME_TOKEN' \\\n"
        "  --header 'Cookie: _session_id=REPLACE_ME; "
        "_session_id=REPLACE_ME'"
    ),
)


# ── Registry ──────────────────────────────────────────────────────────────────
BRAND_CONFIGS: Dict[str, BrandConfig] = {
    'B1': B1_CONFIG,
    'B2': B2_CONFIG,
}
SUPPORTED_BRANDS = list(BRAND_CONFIGS.keys())


def get_brand_config(brand_code: str) -> BrandConfig:
    """Return config for a brand code (case-insensitive)."""
    code = brand_code.upper().strip()
    if code not in BRAND_CONFIGS:
        raise ValueError(f"Unsupported brand '{brand_code}'. Supported: {SUPPORTED_BRANDS}")
    return BRAND_CONFIGS[code]


# ══════════════════════════════════════════════════════════════════════════════
# 3. VALIDATOR ENGINE  —  Location vs Master product mapping
# ══════════════════════════════════════════════════════════════════════════════

def load_json_file(file_path: str) -> dict:
    """Load JSON from file. Handles B2-style bare 'mappingLookup' fragments."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    if content.startswith('"mappingLookup"') or content.startswith("'mappingLookup'"):
        if content.endswith(','):
            content = content[:-1]
        content = '{' + content + '}'
    return json.loads(content)


def _detect_menu_key(data: dict, brand_code: str) -> str:
    """Return the first key inside data['menus'], preferring the brand prefix."""
    menus = data.get('menus', {})
    if not menus:
        raise KeyError(f"No 'menus' key found in location data for {brand_code}")
    keys = list(menus.keys())
    if len(keys) == 1:
        return keys[0]
    prefix = brand_code.lower()
    for k in keys:
        if k.lower().startswith(prefix):
            return k
    return keys[0]


def _extract_product_id_from_ref(ref_string: str):
    """Extract (type, id) from 'products.bacon-b79f9b6a' style refs."""
    if not ref_string or '.' not in ref_string:
        return None, None
    parts = ref_string.split('.', 1)
    return parts[0], parts[1] if len(parts) > 1 else None


def extract_all_products(location_data: dict, brand_code: str) -> dict:
    """
    Extract all products from the location menu:
      1. main products
      2. productGroups -> childRefs
      3. ingredientRefs
      4. alternatives
      5. modifierGroupRefs
    """
    all_products = defaultdict(lambda: {
        'product_id': '', 'display_name': '', 'is_virtual': False,
        'is_recipe': False, 'is_default': False,
        'quantity_min': None, 'quantity_max': None,
        'source': set(), 'found_in_groups': [], 'used_by': [],
    })

    menu_key       = _detect_menu_key(location_data, brand_code)
    menu_data      = location_data.get('menus', {}).get(menu_key, {})
    products       = menu_data.get('products', {})
    product_groups = menu_data.get('productGroups', {})

    # 1 — Main products
    for pid, details in products.items():
        p = all_products[pid]
        p['product_id']   = pid
        p['display_name'] = details.get('displayName', '')
        p['is_virtual']   = details.get('isVirtual', False)
        qty = details.get('quantity', {})
        p['quantity_min'] = qty.get('min') if isinstance(qty, dict) else None
        p['quantity_max'] = qty.get('max') if isinstance(qty, dict) else None
        p['source'].add('main_products')

    # 2 — productGroups -> childRefs
    for group_id, group_details in product_groups.items():
        child_refs      = group_details.get('childRefs', {})
        group_name      = group_details.get('displayName', group_id)
        group_is_recipe = group_details.get('isRecipe', False)
        for child_ref, child_ref_entry in child_refs.items():
            ref_type, ref_id = _extract_product_id_from_ref(child_ref)
            if ref_type == 'products' and ref_id:
                p = all_products[ref_id]
                p['source'].add('productGroup_child')
                p['found_in_groups'].append(group_name)
                if group_is_recipe:
                    p['is_recipe'] = True
                if isinstance(child_ref_entry, dict):
                    if child_ref_entry.get('isDefault', False):
                        p['is_default'] = True
                    qty = child_ref_entry.get('quantity', {})
                    if isinstance(qty, dict) and qty:
                        p['quantity_min'] = qty.get('min')
                        p['quantity_max'] = qty.get('max')

    # 3 — ingredientRefs
    for pid, details in products.items():
        for ing_ref in details.get('ingredientRefs', {}).keys():
            ref_type, ref_id = _extract_product_id_from_ref(ing_ref)
            if ref_type == 'products' and ref_id:
                all_products[ref_id]['source'].add('ingredientRef')

    # 4 — alternatives
    for pid, details in products.items():
        related = details.get('relatedProducts', {})
        for alt_ref in related.get('alternatives', {}).keys():
            ref_type, ref_id = _extract_product_id_from_ref(alt_ref)
            if ref_type == 'products' and ref_id:
                all_products[ref_id]['source'].add('alternative')

    # 5 — modifierGroupRefs
    for pid, details in products.items():
        for mod_ref in details.get('modifierGroupRefs', {}).keys():
            ref_type, ref_id = _extract_product_id_from_ref(mod_ref)
            if ref_type == 'products' and ref_id:
                all_products[ref_id]['source'].add('modifierGroupRef')

    # 6 — used_by: which parent products reference each child via ingredientRefs -> productGroups -> childRefs
    # Step A: group_id -> set of parent product display names
    group_to_parents: dict = {}
    for pid, details in products.items():
        parent_name = details.get('displayName', pid)
        for ing_ref in details.get('ingredientRefs', {}).keys():
            if '.' in ing_ref:
                _, grp_id = ing_ref.split('.', 1)
                group_to_parents.setdefault(grp_id, set()).add(parent_name)
    # Step B: assign used_by to each child product
    for grp_id, grp_details in product_groups.items():
        for child_ref in grp_details.get('childRefs', {}).keys():
            ref_type, ref_id = _extract_product_id_from_ref(child_ref)
            if ref_type == 'products' and ref_id and grp_id in group_to_parents:
                for pname in group_to_parents[grp_id]:
                    if pname not in all_products[ref_id]['used_by']:
                        all_products[ref_id]['used_by'].append(pname)

    return all_products


def check_mapping(product_id: str, master_data: dict, brand_cfg: BrandConfig) -> dict:
    """
    Check if a product has a posId mapping in the master menu.
      1. Direct:     mappingLookup[product_id]
      2. Contextual: mappingLookup["parent#product_id"]
    """
    mapping_lookup = master_data.get('mappingLookup', {})
    primary = brand_cfg.primary_mapping_field
    extras  = brand_cfg.extra_mapping_fields

    def _extract_fields(entry: dict) -> dict:
        result = {primary: entry.get(primary, '')}
        for f in extras:
            result[f] = entry.get(f, '')
        return result

    # Direct
    product_mapping = mapping_lookup.get(product_id, {})
    if isinstance(product_mapping, list):
        product_mapping = product_mapping[0] if product_mapping else {}
    if isinstance(product_mapping, dict) and product_mapping.get(primary, ''):
        return {'is_mapped': True, 'mapping_type': 'Direct',
                'contextual_parents': [], **_extract_fields(product_mapping)}

    # Contextual
    contextual_parents = []
    ctx_fields: dict = {}
    for key, val in mapping_lookup.items():
        if '#' in key:
            _parent, child = key.split('#', 1)
            if child == product_id:
                contextual_parents.append(_parent)
                if not ctx_fields:
                    entry = val[0] if isinstance(val, list) and val else val
                    if isinstance(entry, dict):
                        ctx_fields = _extract_fields(entry)
    if contextual_parents:
        return {'is_mapped': True, 'mapping_type': 'Contextual',
                'contextual_parents': contextual_parents,
                **(ctx_fields or {primary: '', **{f: '' for f in extras}})}

    # Not mapped
    return {'is_mapped': False, 'mapping_type': 'Not Mapped',
            'contextual_parents': [], primary: '', **{f: '' for f in extras}}


def _field_display_name(field_key: str) -> str:
    """Convert camelCase field key to Title Case column header."""
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', field_key)
    return spaced.replace('Id', 'ID').title().replace(' Id', ' ID')


def _get_category(display_name: str, groups_list: list, brand_cfg: BrandConfig) -> str:
    if groups_list:
        return groups_list[0]
    name = display_name.lower()
    for category, keywords in brand_cfg.category_keywords.items():
        if any(w in name for w in keywords):
            return category
    return 'Other'


def _build_contextual_rows(mapping_lookup, product_name_map, all_products, extras):
    rows = []
    for key, val in sorted(mapping_lookup.items()):
        if '#' not in key:
            continue
        parent_id, child_id = key.split('#', 1)
        entry      = val[0] if isinstance(val, list) and val else val
        entry      = entry if isinstance(entry, dict) else {}
        child_info = all_products.get(child_id, {})
        row = {
            'Contextual Key': key,
            'Parent Product ID': parent_id,
            'Child Product ID': child_id,
            'Child Display Name': product_name_map.get(child_id, ''),
            'POS ID': entry.get('posId', ''),
        }
        for ef in extras:
            row[_field_display_name(ef)] = entry.get(ef, '')
        row.update({
            'Is Virtual': child_info.get('is_virtual', False),
            'Is Recipe':  child_info.get('is_recipe', False),
            'Is Default': child_info.get('is_default', False),
            'Qty Min':    child_info.get('quantity_min'),
            'Qty Max':    child_info.get('quantity_max'),
        })
        rows.append(row)
    return rows


def _build_rca_rows(df, mapping_lookup, master_data, all_products, brand_cfg: BrandConfig):
    master_str = json.dumps(master_data)
    rows = []
    for _, row in df[df['Mapping Status'] == 'Mapping not found'].iterrows():
        pid        = row['Product ID']
        name       = row['Display Name']
        name_words = [w for w in name.lower().split() if len(w) > 3]
        similar_keys = [k for k in mapping_lookup if any(w in k.lower() for w in name_words)]
        appears    = pid in master_str
        if similar_keys:
            root_cause = 'Similar name exists in master but with different product ID/key'
            action     = 'Verify if sized variants should cover this generic product'
        elif not appears:
            root_cause = 'Product ID completely absent from Master Menu'
            action     = 'Add new mappingLookup entry in Master'
        else:
            root_cause = 'Product ID present in master body but missing from mappingLookup'
            action     = 'Add posId mapping entry in mappingLookup'
        rows.append({
            'Product ID': pid,
            'Display Name': name,
            'Category': _get_category(name, [], brand_cfg),
            'isVirtual': row['Is Virtual'],
            'Found in Groups': row['Found in Groups'],
            'Appears in Master': 'Yes (but no mappingLookup entry)' if appears else 'No — completely missing',
            'Similar Keys in Master': ', '.join(similar_keys[:5]) if similar_keys else 'None',
            'Root Cause': root_cause,
            'Recommended Action': action,
        })
    return rows


def _build_json_payload(brand_cfg, df, all_products, master_data, timestamp, stats, location_id=''):
    total  = stats['total']
    mapped = stats['mapped']
    nv     = stats['non_virtual']
    nv_m   = stats['nv_mapped']
    extras = brand_cfg.extra_mapping_fields

    json_data = {
        'metadata': {
            'brand': brand_cfg.brand_code,
            'brandName': brand_cfg.brand_name,
            'timestamp': timestamp,
            'generated_at': datetime.now().isoformat(),
            'location_id': location_id or None,
            'total_products': total,
            'virtual_products': stats['virtual'],
            'non_virtual_products': nv,
            'mapped_count': mapped,
            'direct_mapped_count': stats['direct'],
            'contextual_mapped_count': stats['contextual'],
            'unmapped_count': stats['unmapped'],
            'non_virtual_unmapped': stats['nv_unmapped'],
            'mapping_coverage_all': f'{mapped/total*100:.2f}%' if total else '0%',
            'mapping_coverage_non_virtual': f'{nv_m/nv*100:.2f}%' if nv else 'N/A',
            'products_in_groups': stats['in_groups'],
            'products_main_only': stats['main_only'],
        },
        'products': [],
        'contextualPaths': [],
    }

    for _, row in df.iterrows():
        pid        = row['Product ID']
        pinfo      = all_products.get(pid, {})
        raw_groups = pinfo.get('found_in_groups', [])
        product_entry = {
            'id': pid,
            'displayName': row['Display Name'],
            'category': _get_category(row['Display Name'], raw_groups, brand_cfg),
            'isVirtual': row['Is Virtual'] == 'Yes',
            'isRecipe': pinfo.get('is_recipe', False),
            'isDefault': pinfo.get('is_default', False),
            'quantityMin': pinfo.get('quantity_min'),
            'quantityMax': pinfo.get('quantity_max'),
            'isMapped': row['Mapping Status'] == 'Mapped correctly',
            'mappingType': row['Mapping Type'],
            'source': row['Source'].split(', '),
            'groups': (
                row['Found in Groups'].replace(' (+', '|').replace(' more)', '').split(', ')
                if row['Found in Groups'] else []
            ),
            'usedBy': sorted(pinfo.get('used_by', [])),
            'contextualParents': (
                row['Contextual Parents'].split(', ') if row['Contextual Parents'] else []
            ),
            'contextualParentCount': int(row['Contextual Parent Count']),
            'posId': row['POS ID'],
        }
        for ef in extras:
            product_entry[ef] = row.get(_field_display_name(ef), '')
        json_data['products'].append(product_entry)

    mapping_lookup   = master_data.get('mappingLookup', {})
    product_name_map = {pid: info['display_name'] for pid, info in all_products.items()}
    for key, val in sorted(mapping_lookup.items()):
        if '#' not in key:
            continue
        parent_id, child_id = key.split('#', 1)
        entry      = val[0] if isinstance(val, list) and val else val
        entry      = entry if isinstance(entry, dict) else {}
        child_info = all_products.get(child_id, {})
        path_entry = {
            'contextualKey': key,
            'parentProductId': parent_id,
            'childProductId': child_id,
            'childDisplayName': product_name_map.get(child_id, ''),
            'posId': entry.get('posId', ''),
            'isVirtual': child_info.get('is_virtual', False),
            'isRecipe':  child_info.get('is_recipe', False),
            'isDefault': child_info.get('is_default', False),
            'quantityMin': child_info.get('quantity_min'),
            'quantityMax': child_info.get('quantity_max'),
        }
        for ef in extras:
            path_entry[ef] = entry.get(ef, '')
        json_data['contextualPaths'].append(path_entry)

    return json_data


def validate_mappings(
    brand_code: str = 'B1',
    location_file: Optional[str] = None,
    master_file: Optional[str] = None,
    output_dir: Optional[str] = None,
    location_id: str = '',
) -> Tuple[pd.DataFrame, dict]:
    """Run full mapping validation for a given brand. Returns (DataFrame, json_data)."""
    brand_cfg = get_brand_config(brand_code)
    loc_file  = location_file or brand_cfg.default_location_file
    mst_file  = master_file   or brand_cfg.default_master_file
    out_dir   = output_dir    or os.path.join(OUTPUT_ROOT, brand_code)
    os.makedirs(out_dir, exist_ok=True)

    primary = brand_cfg.primary_mapping_field
    extras  = brand_cfg.extra_mapping_fields

    print("=" * 80)
    print(f"UNIFIED PRODUCT MAPPING VALIDATOR  —  {brand_cfg.brand_emoji} {brand_cfg.brand_name}")
    print("=" * 80)
    print()
    print("Loading data files...")
    location_data = load_json_file(loc_file)
    master_data   = load_json_file(mst_file)
    print(f"  Location : {loc_file}")
    print(f"  Master   : {mst_file}")
    print()
    print("Extracting products from all sources...")
    all_products = extract_all_products(location_data, brand_code)
    print(f"  Found {len(all_products)} unique products")
    print()

    validation_results = []
    for pid, pinfo in all_products.items():
        mapping     = check_mapping(pid, master_data, brand_cfg)
        ctx_parents = mapping.get('contextual_parents', [])
        row = {
            'Product ID': pid,
            'Display Name': pinfo['display_name'],
            'Is Virtual': 'Yes' if pinfo['is_virtual'] else 'No',
            'Source': ', '.join(sorted(pinfo['source'])),
            'Found in Groups': (
                ', '.join(pinfo['found_in_groups'][:3])
                + (f' (+{len(pinfo["found_in_groups"])-3} more)' if len(pinfo['found_in_groups']) > 3 else '')
            ),
            'Mapping Status': 'Mapped correctly' if mapping['is_mapped'] else 'Mapping not found',
            'Mapping Type': mapping['mapping_type'],
            'Contextual Parents': (
                ', '.join(ctx_parents[:3])
                + (f' (+{len(ctx_parents)-3} more)' if len(ctx_parents) > 3 else '')
            ) if ctx_parents else '',
            'Contextual Parent Count': len(ctx_parents),
            'POS ID': mapping.get(primary, ''),
            'Used By': ', '.join(sorted(pinfo.get('used_by', []))),
        }
        for ef in extras:
            row[_field_display_name(ef)] = mapping.get(ef, '')
        validation_results.append(row)

    df = pd.DataFrame(validation_results)

    total         = len(df)
    virtual_count = len(df[df['Is Virtual'] == 'Yes'])
    non_virtual   = len(df[df['Is Virtual'] == 'No'])
    mapped        = len(df[df['Mapping Status'] == 'Mapped correctly'])
    unmapped      = len(df[df['Mapping Status'] == 'Mapping not found'])
    direct_mapped = len(df[df['Mapping Type'] == 'Direct'])
    ctx_mapped    = len(df[df['Mapping Type'] == 'Contextual'])
    nv_df         = df[df['Is Virtual'] == 'No']
    nv_mapped     = len(nv_df[nv_df['Mapping Status'] == 'Mapped correctly'])
    nv_unmapped   = len(nv_df[nv_df['Mapping Status'] == 'Mapping not found'])
    in_groups     = len(df[df['Found in Groups'] != ''])
    main_only     = total - in_groups

    print("=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Total Products:           {total}")
    print(f"  Virtual Products:       {virtual_count}")
    print(f"  Non-Virtual:            {non_virtual}")
    print()
    print(f"Mapped:                   {mapped} ({mapped/total*100:.2f}%)")
    print(f"  Direct:                 {direct_mapped}")
    print(f"  Contextual:             {ctx_mapped}")
    print(f"Unmapped:                 {unmapped} ({unmapped/total*100:.2f}%)")
    print()
    if non_virtual > 0:
        print(f"Non-Virtual Mapped:       {nv_mapped} ({nv_mapped/non_virtual*100:.2f}%)")
        print(f"Non-Virtual Unmapped:     {nv_unmapped} ({nv_unmapped/non_virtual*100:.2f}%)")
        print()

    unmapped_df = df[df['Mapping Status'] == 'Mapping not found']
    if len(unmapped_df) > 0:
        print(f"UNMAPPED PRODUCTS ({len(unmapped_df)} items)")
        print("-" * 40)
        for _, r in unmapped_df.iterrows():
            print(f"  {r['Product ID']}  |  {r['Display Name']}  |  Virtual: {r['Is Virtual']}")
        print()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    loc_part  = f'_{location_id}' if location_id else ''
    xlsx_file = os.path.join(out_dir, f'{brand_code}{loc_part}_Validation_{timestamp}.xlsx')
    nv_pct    = f'{nv_mapped/non_virtual*100:.2f}%' if non_virtual > 0 else 'N/A'

    with pd.ExcelWriter(xlsx_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='All Products', index=False)
        nv_df.to_excel(writer, sheet_name='Non-Virtual Products', index=False)
        df[df['Mapping Status'] == 'Mapped correctly'].to_excel(writer, sheet_name='Mapped Products', index=False)
        df[df['Mapping Status'] == 'Mapping not found'].to_excel(writer, sheet_name='Unmapped Products', index=False)
        df[df['Found in Groups'] != ''].to_excel(writer, sheet_name='Products in Groups', index=False)
        pd.DataFrame({
            'Metric': [
                'Brand', 'Location ID', 'Total Products', 'Virtual Products', 'Non-Virtual Products',
                'Mapped Products (Total)', '  Direct Mapped', '  Contextual Mapped',
                'Unmapped Products', 'Products in ProductGroups', 'Products Main Menu Only',
                'Non-Virtual Mapped', 'Non-Virtual Unmapped',
                'Mapping Coverage (All)', 'Mapping Coverage (Non-Virtual)',
            ],
            'Count': [
                brand_cfg.brand_name, location_id or 'N/A', total, virtual_count, non_virtual,
                mapped, direct_mapped, ctx_mapped, unmapped, in_groups, main_only,
                nv_mapped, nv_unmapped, f'{mapped/total*100:.2f}%', nv_pct,
            ],
        }).to_excel(writer, sheet_name='Summary', index=False)
        mapping_lookup   = master_data.get('mappingLookup', {})
        product_name_map = {pid: info['display_name'] for pid, info in all_products.items()}
        pd.DataFrame(_build_contextual_rows(mapping_lookup, product_name_map, all_products, extras)).to_excel(
            writer, sheet_name='Contextual Mappings', index=False)
        pd.DataFrame(_build_rca_rows(df, mapping_lookup, master_data, all_products, brand_cfg)).to_excel(
            writer, sheet_name='Root Cause Analysis', index=False)

    print(f"Excel report : {xlsx_file}")

    json_file = os.path.join(out_dir, f'Unified_Validation_Report_{timestamp}.json')
    stats_dict = {
        'total': total, 'virtual': virtual_count, 'non_virtual': non_virtual,
        'mapped': mapped, 'unmapped': unmapped,
        'direct': direct_mapped, 'contextual': ctx_mapped,
        'nv_mapped': nv_mapped, 'nv_unmapped': nv_unmapped,
        'in_groups': in_groups, 'main_only': main_only,
    }
    json_data = _build_json_payload(
        brand_cfg, df, all_products, master_data,
        timestamp=timestamp, location_id=location_id, stats=stats_dict,
    )
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON report  : {json_file}")
    print()

    return df, json_data


# ══════════════════════════════════════════════════════════════════════════════
# 4. MASTER DELTA ENGINE  —  UAT Master vs PROD Master comparison
# ══════════════════════════════════════════════════════════════════════════════

DELTA_STATUS_UAT_ONLY  = 'UAT Only'
DELTA_STATUS_PROD_ONLY = 'PROD Only'
DELTA_STATUS_MODIFIED  = 'Modified'
DELTA_STATUS_MATCHED   = 'Matched'


def _normalise_entry(entry: Any) -> dict:
    if isinstance(entry, list):
        entry = entry[0] if entry else {}
    return entry if isinstance(entry, dict) else {}


def _entries_equal(e1: dict, e2: dict, fields: List[str]) -> bool:
    return all(str(e1.get(f, '')).strip() == str(e2.get(f, '')).strip() for f in fields)


def _build_field_diff(uat_entry: dict, prod_entry: dict, fields: List[str]) -> str:
    diffs = []
    for f in fields:
        v1 = str(uat_entry.get(f, '')).strip()
        v2 = str(prod_entry.get(f, '')).strip()
        if v1 != v2:
            diffs.append(f"{f}: '{v1}' -> '{v2}'")
    return ' | '.join(diffs) if diffs else ''


def compare_masters(
    brand_code: str,
    uat_data: dict,
    prod_data: dict,
    output_dir: Optional[str] = None,
) -> Tuple[pd.DataFrame, dict]:
    """Compare UAT vs PROD master mappingLookup. Returns (DataFrame, json_data)."""
    brand_cfg  = get_brand_config(brand_code)
    out_dir    = output_dir or os.path.join(OUTPUT_ROOT, brand_code.upper(), 'MasterDelta')
    os.makedirs(out_dir, exist_ok=True)

    primary    = brand_cfg.primary_mapping_field
    extras     = brand_cfg.extra_mapping_fields
    all_fields = [primary] + extras

    uat_lookup  = uat_data.get('mappingLookup', {})
    prod_lookup = prod_data.get('mappingLookup', {})
    all_keys    = sorted(set(list(uat_lookup.keys()) + list(prod_lookup.keys())))

    rows = []
    for key in all_keys:
        in_uat     = key in uat_lookup
        in_prod    = key in prod_lookup
        uat_entry  = _normalise_entry(uat_lookup.get(key,  {}))
        prod_entry = _normalise_entry(prod_lookup.get(key, {}))

        if in_uat and in_prod:
            status = DELTA_STATUS_MATCHED if _entries_equal(uat_entry, prod_entry, all_fields) else DELTA_STATUS_MODIFIED
        elif in_uat:
            status = DELTA_STATUS_UAT_ONLY
        else:
            status = DELTA_STATUS_PROD_ONLY

        is_ctx    = '#' in key
        parent_id = key.split('#', 1)[0] if is_ctx else ''
        child_id  = key.split('#', 1)[1] if is_ctx else ''

        row = {
            'Key': key,
            'Is Contextual': 'Yes' if is_ctx else 'No',
            'Parent ID': parent_id,
            'Child ID': child_id,
            'Delta Status': status,
            'Field Diff': _build_field_diff(uat_entry, prod_entry, all_fields) if status == DELTA_STATUS_MODIFIED else '',
        }
        for f in all_fields:
            row[f'UAT {f}']  = uat_entry.get(f, '')  if in_uat  else '—'
            row[f'PROD {f}'] = prod_entry.get(f, '') if in_prod else '—'
        rows.append(row)

    df = pd.DataFrame(rows)

    total         = len(df)
    uat_only_cnt  = len(df[df['Delta Status'] == DELTA_STATUS_UAT_ONLY])
    prod_only_cnt = len(df[df['Delta Status'] == DELTA_STATUS_PROD_ONLY])
    modified_cnt  = len(df[df['Delta Status'] == DELTA_STATUS_MODIFIED])
    matched_cnt   = len(df[df['Delta Status'] == DELTA_STATUS_MATCHED])
    ctx_count     = len(df[df['Is Contextual'] == 'Yes'])
    direct_count  = len(df[df['Is Contextual'] == 'No'])
    sync_pct      = f"{matched_cnt / total * 100:.2f}%" if total else "0%"

    print("=" * 80)
    print(f"MASTER DELTA REPORT  —  {brand_cfg.brand_emoji} {brand_cfg.brand_name}")
    print("=" * 80)
    print(f"  UAT mapping keys    : {len(uat_lookup)}")
    print(f"  PROD mapping keys   : {len(prod_lookup)}")
    print(f"  Total unique keys   : {total}")
    print()
    print(f"  UAT Only            : {uat_only_cnt}")
    print(f"  PROD Only           : {prod_only_cnt}")
    print(f"  Modified            : {modified_cnt}")
    print(f"  Matched             : {matched_cnt}")
    print()
    print(f"  Direct keys         : {direct_count}")
    print(f"  Contextual keys     : {ctx_count}")
    print(f"  Sync health         : {sync_pct}")
    print()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    xlsx_path = os.path.join(out_dir, f'Master_Delta_Report_{timestamp}.xlsx')

    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        pd.DataFrame({
            'Metric': [
                'Brand', 'Report Generated',
                'UAT Master Keys', 'PROD Master Keys', 'Total Unique Keys',
                'UAT Only', 'PROD Only', 'Modified', 'Matched',
                'Direct Keys', 'Contextual Keys', 'Sync Health %',
            ],
            'Value': [
                brand_cfg.brand_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                len(uat_lookup), len(prod_lookup), total,
                uat_only_cnt, prod_only_cnt, modified_cnt, matched_cnt,
                direct_count, ctx_count, sync_pct,
            ],
        }).to_excel(writer, sheet_name='Summary', index=False)
        df.to_excel(writer, sheet_name='All Keys', index=False)
        for status, sheet_name in [
            (DELTA_STATUS_UAT_ONLY,  'UAT Only'),
            (DELTA_STATUS_PROD_ONLY, 'PROD Only'),
            (DELTA_STATUS_MODIFIED,  'Modified'),
            (DELTA_STATUS_MATCHED,   'Matched'),
        ]:
            df[df['Delta Status'] == status].to_excel(writer, sheet_name=sheet_name, index=False)
        df[df['Is Contextual'] == 'Yes'].to_excel(writer, sheet_name='Contextual Delta', index=False)

    print(f"Excel report : {xlsx_path}")

    json_path = os.path.join(out_dir, f'Master_Delta_Report_{timestamp}.json')
    entries = []
    for _, row in df.iterrows():
        entry = {
            'key': row['Key'], 'isContextual': row['Is Contextual'] == 'Yes',
            'parentId': row['Parent ID'], 'childId': row['Child ID'],
            'deltaStatus': row['Delta Status'], 'fieldDiff': row['Field Diff'],
        }
        for f in all_fields:
            entry[f'uat_{f}']  = row.get(f'UAT {f}',  '')
            entry[f'prod_{f}'] = row.get(f'PROD {f}', '')
        entries.append(entry)

    json_data = {
        'metadata': {
            'brand': brand_cfg.brand_code, 'brandName': brand_cfg.brand_name,
            'timestamp': timestamp, 'generated_at': datetime.now().isoformat(),
            'uat_key_count': len(uat_lookup), 'prod_key_count': len(prod_lookup),
            'total_unique_keys': total,
            'uat_only_count': uat_only_cnt, 'prod_only_count': prod_only_cnt,
            'modified_count': modified_cnt, 'matched_count': matched_cnt,
            'direct_key_count': direct_count, 'contextual_key_count': ctx_count,
            'sync_health_pct': sync_pct, 'all_fields': all_fields,
        },
        'entries': entries,
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON report  : {json_path}")
    print()

    return df, json_data


def get_latest_delta_json(brand: str) -> Optional[str]:
    """Return path to the most recent Master Delta JSON report for a brand."""
    d       = os.path.join(OUTPUT_ROOT, brand.upper(), 'MasterDelta')
    pattern = os.path.join(d, 'Master_Delta_Report_*.json')
    files   = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=lambda x: Path(x).stat().st_mtime)


# ══════════════════════════════════════════════════════════════════════════════
# 5. FLASK API SERVER
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)

validation_cache = {brand: {'data': None, 'last_updated': None} for brand in SUPPORTED_BRANDS}
delta_cache      = {brand: {'data': None, 'last_updated': None} for brand in SUPPORTED_BRANDS}

MAX_HISTORY = 5


def _brand_report_dir(brand: str) -> str:
    return os.path.join('Reports', brand.upper())


def _get_latest_json(brand: str):
    d       = _brand_report_dir(brand)
    pattern = os.path.join(d, 'Unified_Validation_Report_*.json')
    files   = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=lambda x: Path(x).stat().st_mtime)


def _prune_old_reports(directory: str, json_pattern: str) -> None:
    """Keep only MAX_HISTORY newest report pairs (.json + .xlsx)."""
    json_files = glob.glob(os.path.join(directory, json_pattern))
    if len(json_files) <= MAX_HISTORY:
        return
    json_files.sort(key=lambda x: Path(x).stat().st_mtime)
    for jf in json_files[:len(json_files) - MAX_HISTORY]:
        try:
            os.remove(jf)
        except Exception:
            pass
        xlsx = jf.replace('.json', '.xlsx')
        if os.path.exists(xlsx):
            try:
                os.remove(xlsx)
            except Exception:
                pass


def _resolve_brand(brand_str, default='B1') -> str:
    brand = (brand_str or default).upper().strip()
    return brand if brand in SUPPORTED_BRANDS else None


def _get_data(brand):
    data = validation_cache[brand]['data']
    if data:
        return data
    latest = _get_latest_json(brand)
    if latest:
        with open(latest, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


# ── Root ──────────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect('/dashboard')


@app.route('/api')
def api_info():
    return jsonify({
        'api': 'Multi-Brand Menu Mapping Validator API', 'version': '3.0',
        'supported_brands': SUPPORTED_BRANDS,
        'endpoints': {
            '/dashboard':                               'GET  - Web dashboard',
            '/api/<brand>/unmapped/live':              'GET  - Live unavailable_products via server-side auth',
            '/api/<brand>/validation/live':             'GET  - Run live validation',
            '/api/<brand>/validation/latest':           'GET  - Latest saved report',
            '/api/<brand>/products':                    'GET  - All products',
            '/api/<brand>/products/mapped':             'GET  - Mapped only',
            '/api/<brand>/products/unmapped':           'GET  - Unmapped only',
            '/api/<brand>/stats':                       'GET  - Summary statistics',
            '/api/<brand>/compare/upload':              'POST - Upload location + master files',
            '/api/<brand>/compare/live':                'POST - Live cURL compare',
            '/api/<brand>/reports/history':             'GET  - List saved validation reports',
            '/api/<brand>/reports/load/<f>':            'GET  - Load saved validation report',
            '/api/<brand>/reports/download/<f>':        'GET  - Download report file',
            '/api/<brand>/master-delta/compare/live':   'POST - Live UAT vs PROD delta',
            '/api/<brand>/master-delta/compare/upload': 'POST - Upload UAT vs PROD delta',
            '/api/<brand>/delta-reports/history':       'GET  - List saved delta reports',
            '/api/<brand>/delta-reports/load/<f>':      'GET  - Load saved delta report',
            '/api/brands':                              'GET  - Brand configs',
            '/api/proxy':                               'GET  - CORS proxy',
        },
    })


# ── Brands ────────────────────────────────────────────────────────────────────

@app.route('/api/brands')
def list_brands():
    brands = []
    for code, cfg in BRAND_CONFIGS.items():
        brands.append({
            'code': cfg.brand_code, 'name': cfg.brand_name, 'emoji': cfg.brand_emoji,
            'logoUrl': cfg.logo_url, 'primaryColor': cfg.primary_color,
            'primaryDark': cfg.primary_dark, 'gradientStart': cfg.gradient_start,
            'gradientEnd': cfg.gradient_end, 'sampleLocationId': cfg.sample_location_id,
            'sampleCurlLocation': cfg.sample_curl_location,
            'sampleCurlMaster': cfg.sample_curl_master,
            'extraMappingFields': cfg.extra_mapping_fields,
            'sampleCurlDeltaUat': cfg.sample_curl_delta_uat,
            'sampleCurlDeltaProd': cfg.sample_curl_delta_prod,
        })
    return jsonify({'status': 'success', 'brands': brands})


# ── Validation endpoints ──────────────────────────────────────────────────────

@app.route('/api/<brand_code>/validation/live')
def brand_live_validation(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    try:
        cfg = get_brand_config(brand)
        df, json_data = validate_mappings(brand_code=brand)
        validation_cache[brand]['data'] = json_data
        validation_cache[brand]['last_updated'] = datetime.now().isoformat()
        return jsonify({'status': 'success', 'brand': brand,
                        'message': f'{cfg.brand_name} live validation completed',
                        'timestamp': validation_cache[brand]['last_updated'], 'data': json_data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/<brand_code>/validation/cached')
def brand_cached_validation(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    cache = validation_cache[brand]
    if cache['data'] is None:
        return jsonify({'status': 'error', 'message': f'No cached data for {brand}.'}), 404
    return jsonify({'status': 'success', 'brand': brand,
                    'timestamp': cache['last_updated'], 'data': cache['data']})


@app.route('/api/<brand_code>/validation/latest')
def brand_latest_validation(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    latest = _get_latest_json(brand)
    if not latest:
        return jsonify({'status': 'error', 'message': f'No validation JSON for {brand}.'}), 404
    with open(latest, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({'status': 'success', 'brand': brand, 'file': latest, 'data': data})


@app.route('/api/<brand_code>/products')
def brand_products(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    data = _get_data(brand)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data available'}), 404
    return jsonify({'status': 'success', 'brand': brand,
                    'count': len(data['products']), 'products': data['products']})


@app.route('/api/<brand_code>/products/mapped')
def brand_mapped(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    data = _get_data(brand)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data available'}), 404
    mapped = [p for p in data['products'] if p['isMapped']]
    return jsonify({'status': 'success', 'brand': brand, 'count': len(mapped), 'products': mapped})


@app.route('/api/<brand_code>/products/unmapped')
def brand_unmapped(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    data = _get_data(brand)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data available'}), 404
    unmapped = [p for p in data['products'] if not p['isMapped']]
    return jsonify({'status': 'success', 'brand': brand, 'count': len(unmapped), 'products': unmapped})


@app.route('/api/<brand_code>/stats')
def brand_stats(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    data = _get_data(brand)
    if not data:
        return jsonify({'status': 'error', 'message': 'No data available'}), 404
    return jsonify({'status': 'success', 'brand': brand, 'statistics': data['metadata']})


@app.route('/api/<brand_code>/unmapped/live')
def brand_unmapped_live(brand_code):
    """Fetch unavailable_products from MenuApi using server-side auth headers/cookies."""
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400

    location_id = (request.args.get('location_id') or '').strip()
    event_type = (request.args.get('event_type') or 'unavailable_products').strip()
    if not location_id:
        return jsonify({'status': 'error', 'message': 'location_id is required'}), 400

    cfg = get_brand_config(brand)
    target_url = (
        f"{cfg.api_base_url}?location_id={location_id}&brand={brand}&event_type={event_type}"
    )

    primary_token = (cfg.prod_master_token or cfg.api_auth_token or '').strip()
    fallback_token = (cfg.api_auth_token or '').strip()
    cookie_header = (cfg.prod_master_cookie or '').strip()

    def _call(token: str):
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        if cookie_header:
            headers['Cookie'] = cookie_header
        return http_requests.get(target_url, headers=headers, timeout=120, verify=not _INSECURE_TLS)

    try:
        resp = _call(primary_token)
        if resp.status_code == 401 and fallback_token and fallback_token != primary_token:
            resp = _call(fallback_token)

        try:
            payload = resp.json()
        except Exception:
            payload = {'raw': resp.text}

        if resp.status_code >= 400:
            return jsonify({
                'status': 'error',
                'brand': brand,
                'http_status': resp.status_code,
                'url': target_url,
                'message': f'MenuApi request failed: HTTP {resp.status_code}',
                'body': payload,
            }), 502

        return jsonify({
            'status': 'success',
            'brand': brand,
            'http_status': resp.status_code,
            'url': target_url,
            'body': payload,
        })
    except http_requests.exceptions.Timeout:
        return jsonify({'status': 'error', 'message': 'Timeout while calling MenuApi'}), 504
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Compare endpoints ─────────────────────────────────────────────────────────

@app.route('/api/<brand_code>/compare/upload', methods=['POST'])
def brand_compare_upload(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    if 'uat_file' not in request.files or 'master_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Both uat_file and master_file required'}), 400
    uat_f              = request.files['uat_file']
    master_f           = request.files['master_file']
    upload_location_id = request.form.get('location_id', '').strip()
    tmp_dir  = tempfile.mkdtemp()
    perm_dir = _brand_report_dir(brand)
    os.makedirs(perm_dir, exist_ok=True)
    try:
        uat_path    = os.path.join(tmp_dir, 'location.json')
        master_path = os.path.join(tmp_dir, 'master.json')
        uat_f.save(uat_path)
        master_f.save(master_path)
        load_json_file(uat_path)
        load_json_file(master_path)
        df, json_data = validate_mappings(
            brand_code=brand, location_file=uat_path,
            master_file=master_path, output_dir=perm_dir, location_id=upload_location_id)
        validation_cache[brand]['data'] = json_data
        validation_cache[brand]['last_updated'] = datetime.now().isoformat()
        _prune_old_reports(perm_dir, 'Unified_Validation_Report_*.json')
        return jsonify({'status': 'success', 'brand': brand,
                        'message': 'Comparison completed from uploaded files',
                        'timestamp': validation_cache[brand]['last_updated'], 'data': json_data})
    except json.JSONDecodeError as e:
        return jsonify({'status': 'error', 'message': f'Invalid JSON: {e}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route('/api/<brand_code>/compare/live', methods=['POST'])
def brand_compare_live(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': 'Unsupported brand'}), 400
    body           = request.get_json() or {}
    uat_url        = body.get('uat_url', '').strip()
    master_url     = body.get('master_url', '').strip()
    shared_headers = body.get('headers', {})
    uat_headers    = body.get('uat_headers',    None) or shared_headers
    master_headers = body.get('master_headers', None) or shared_headers
    if not uat_url or not master_url:
        return jsonify({'status': 'error', 'message': 'Both uat_url and master_url required'}), 400
    _parsed_uat      = urlparse(uat_url)
    _qs              = parse_qs(_parsed_uat.query)
    live_location_id = (_qs.get('location_id') or _qs.get('locationId') or [None])[0] or ''
    tmp_dir  = tempfile.mkdtemp()
    perm_dir = _brand_report_dir(brand)
    os.makedirs(perm_dir, exist_ok=True)
    try:
        uat_resp = http_requests.get(uat_url, headers=uat_headers, timeout=120, verify=not _INSECURE_TLS)
        uat_resp.raise_for_status()
        uat_path = os.path.join(tmp_dir, 'location_live.txt')
        with open(uat_path, 'w', encoding='utf-8') as f:
            f.write(uat_resp.text)
        master_resp = http_requests.get(master_url, headers=master_headers, timeout=120, verify=not _INSECURE_TLS)
        master_resp.raise_for_status()
        master_path = os.path.join(tmp_dir, 'master_live.txt')
        with open(master_path, 'w', encoding='utf-8') as f:
            f.write(master_resp.text)
        df, json_data = validate_mappings(
            brand_code=brand, location_file=uat_path,
            master_file=master_path, output_dir=perm_dir, location_id=live_location_id)
        validation_cache[brand]['data'] = json_data
        validation_cache[brand]['last_updated'] = datetime.now().isoformat()
        _prune_old_reports(perm_dir, 'Unified_Validation_Report_*.json')
        return jsonify({'status': 'success', 'brand': brand,
                        'message': f'{brand} live curl comparison completed',
                        'timestamp': validation_cache[brand]['last_updated'], 'data': json_data})
    except http_requests.exceptions.HTTPError as e:
        return jsonify({'status': 'error', 'message': f'HTTP error: {e}'}), 502
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Master Delta endpoints ────────────────────────────────────────────────────

@app.route('/api/<brand_code>/master-delta/compare/live', methods=['POST'])
def brand_master_delta_live(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    body         = request.get_json() or {}
    uat_url      = body.get('uat_url',  '').strip()
    prod_url     = body.get('prod_url', '').strip()
    shared_hdrs  = body.get('headers', {})
    uat_headers  = body.get('uat_headers',  None) or shared_hdrs
    prod_headers = body.get('prod_headers', None) or shared_hdrs
    if not uat_url or not prod_url:
        return jsonify({'status': 'error', 'message': 'Both uat_url and prod_url are required'}), 400
    tmp_dir  = tempfile.mkdtemp()
    perm_dir = os.path.join('Reports', brand.upper(), 'MasterDelta')
    os.makedirs(perm_dir, exist_ok=True)
    try:
        uat_resp = http_requests.get(uat_url, headers=uat_headers, timeout=120, verify=not _INSECURE_TLS)
        uat_resp.raise_for_status()
        uat_path = os.path.join(tmp_dir, 'uat_master.json')
        with open(uat_path, 'w', encoding='utf-8') as f:
            f.write(uat_resp.text)
        prod_resp = http_requests.get(prod_url, headers=prod_headers, timeout=120, verify=not _INSECURE_TLS)
        prod_resp.raise_for_status()
        prod_path = os.path.join(tmp_dir, 'prod_master.json')
        with open(prod_path, 'w', encoding='utf-8') as f:
            f.write(prod_resp.text)
        uat_data  = load_json_file(uat_path)
        prod_data = load_json_file(prod_path)
        df, json_data = compare_masters(brand_code=brand, uat_data=uat_data,
                                        prod_data=prod_data, output_dir=perm_dir)
        delta_cache[brand]['data']         = json_data
        delta_cache[brand]['last_updated'] = datetime.now().isoformat()
        _prune_old_reports(perm_dir, 'Master_Delta_Report_*.json')
        return jsonify({'status': 'success', 'brand': brand,
                        'message': f'{brand} UAT vs PROD master delta completed',
                        'timestamp': delta_cache[brand]['last_updated'], 'data': json_data})
    except http_requests.exceptions.HTTPError as e:
        return jsonify({'status': 'error', 'message': f'HTTP error: {e}'}), 502
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route('/api/<brand_code>/master-delta/compare/upload', methods=['POST'])
def brand_master_delta_upload(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    if 'uat_file' not in request.files or 'prod_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'Both uat_file and prod_file are required'}), 400
    tmp_dir  = tempfile.mkdtemp()
    perm_dir = os.path.join('Reports', brand.upper(), 'MasterDelta')
    os.makedirs(perm_dir, exist_ok=True)
    try:
        uat_path  = os.path.join(tmp_dir, 'uat_master.json')
        prod_path = os.path.join(tmp_dir, 'prod_master.json')
        request.files['uat_file'].save(uat_path)
        request.files['prod_file'].save(prod_path)
        uat_data  = load_json_file(uat_path)
        prod_data = load_json_file(prod_path)
        df, json_data = compare_masters(brand_code=brand, uat_data=uat_data,
                                        prod_data=prod_data, output_dir=perm_dir)
        delta_cache[brand]['data']         = json_data
        delta_cache[brand]['last_updated'] = datetime.now().isoformat()
        _prune_old_reports(perm_dir, 'Master_Delta_Report_*.json')
        return jsonify({'status': 'success', 'brand': brand,
                        'message': f'{brand} UAT vs PROD master delta completed from uploaded files',
                        'timestamp': delta_cache[brand]['last_updated'], 'data': json_data})
    except json.JSONDecodeError as e:
        return jsonify({'status': 'error', 'message': f'Invalid JSON: {e}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.route('/api/<brand_code>/master-delta/latest')
def brand_master_delta_latest(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    latest = get_latest_delta_json(brand)
    if not latest:
        return jsonify({'status': 'error', 'message': f'No delta report found for {brand}.'}), 404
    with open(latest, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({'status': 'success', 'brand': brand, 'file': latest, 'data': data})


@app.route('/api/<brand_code>/master-delta/stats')
def brand_master_delta_stats(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    data = delta_cache[brand]['data']
    if not data:
        latest = get_latest_delta_json(brand)
        if latest:
            with open(latest, 'r', encoding='utf-8') as f:
                data = json.load(f)
    if not data:
        return jsonify({'status': 'error', 'message': 'No delta data available.'}), 404
    return jsonify({'status': 'success', 'brand': brand, 'statistics': data['metadata']})


# ── History & Download endpoints ──────────────────────────────────────────────

@app.route('/api/<brand_code>/reports/history')
def brand_reports_history(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d          = _brand_report_dir(brand)
    json_files = glob.glob(os.path.join(d, 'Unified_Validation_Report_*.json'))
    reports    = []
    for f in sorted(json_files, key=lambda x: Path(x).stat().st_mtime, reverse=True)[:MAX_HISTORY]:
        fname  = Path(f).name
        ts_str = fname.replace('Unified_Validation_Report_', '').replace('.json', '')
        try:
            dt = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
            display_ts = dt.strftime('%b %d, %Y  %I:%M:%S %p')
        except Exception:
            display_ts = ts_str
        meta = {}
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                meta = json.load(jf).get('metadata', {})
        except Exception:
            pass
        raw_unmapped = meta.get('unmapped_count', 0)
        nv_unmapped  = meta.get('non_virtual_unmapped', None)
        if nv_unmapped is None:
            nv_unmapped = max(0, raw_unmapped - meta.get('virtual_products', 0))
        xlsx_name = fname.replace('.json', '.xlsx')
        reports.append({
            'filename':      fname,
            'timestamp':     display_ts,
            'total':         meta.get('total_products', 0),
            'mapped':        meta.get('mapped_count', 0),
            'unmapped':      nv_unmapped,
            'mapped_pct':    meta.get('mapping_coverage_all', meta.get('mapping_coverage_non_virtual', '—')),
            'location_id':   meta.get('location_id') or '—',
            'has_xlsx':      os.path.exists(os.path.join(d, xlsx_name)),
            'xlsx_filename': xlsx_name if os.path.exists(os.path.join(d, xlsx_name)) else None,
        })
    return jsonify({'status': 'success', 'brand': brand, 'reports': reports})


@app.route('/api/<brand_code>/reports/load/<path:filename>')
def brand_load_report(brand_code, filename):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d         = _brand_report_dir(brand)
    safe_name = Path(filename).name
    full_path = os.path.join(d, safe_name)
    if not os.path.exists(full_path):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    with open(full_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({'status': 'success', 'brand': brand, 'data': data})


@app.route('/api/<brand_code>/reports/download/<path:filename>')
def brand_download_report(brand_code, filename):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d         = _brand_report_dir(brand)
    safe_name = Path(filename).name
    if not os.path.exists(os.path.join(d, safe_name)):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    return send_from_directory(os.path.abspath(d), safe_name, as_attachment=True)


@app.route('/api/<brand_code>/reports/download-latest-xlsx')
def brand_download_latest_xlsx(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d          = _brand_report_dir(brand)
    xlsx_files = glob.glob(os.path.join(d, '*.xlsx'))
    if not xlsx_files:
        return jsonify({'status': 'error', 'message': 'No Excel reports found.'}), 404
    latest = max(xlsx_files, key=lambda x: Path(x).stat().st_mtime)
    return send_from_directory(os.path.abspath(d), Path(latest).name, as_attachment=True)


@app.route('/api/<brand_code>/delta-reports/history')
def brand_delta_reports_history(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d          = os.path.join('Reports', brand.upper(), 'MasterDelta')
    json_files = glob.glob(os.path.join(d, 'Master_Delta_Report_*.json'))
    reports    = []
    for f in sorted(json_files, key=lambda x: Path(x).stat().st_mtime, reverse=True)[:MAX_HISTORY]:
        fname  = Path(f).name
        ts_str = fname.replace('Master_Delta_Report_', '').replace('.json', '')
        try:
            dt = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
            display_ts = dt.strftime('%b %d, %Y  %I:%M:%S %p')
        except Exception:
            display_ts = ts_str
        meta = {}
        try:
            with open(f, 'r', encoding='utf-8') as jf:
                meta = json.load(jf).get('metadata', {})
        except Exception:
            pass
        xlsx_name = fname.replace('.json', '.xlsx')
        reports.append({
            'filename':        fname,
            'timestamp':       display_ts,
            'total':           meta.get('total_unique_keys', meta.get('total_keys', 0)),
            'uat_only':        meta.get('uat_only_count',  meta.get('uat_only',  0)),
            'prod_only':       meta.get('prod_only_count', meta.get('prod_only', 0)),
            'modified':        meta.get('modified_count',  meta.get('modified',  0)),
            'matched':         meta.get('matched_count',   meta.get('matched',   0)),
            'sync_health_pct': meta.get('sync_health_pct', '—'),
            'has_xlsx':        os.path.exists(os.path.join(d, xlsx_name)),
            'xlsx_filename':   xlsx_name if os.path.exists(os.path.join(d, xlsx_name)) else None,
        })
    return jsonify({'status': 'success', 'brand': brand, 'reports': reports})


@app.route('/api/<brand_code>/delta-reports/load/<path:filename>')
def brand_load_delta_report(brand_code, filename):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d         = os.path.join('Reports', brand.upper(), 'MasterDelta')
    safe_name = Path(filename).name
    full_path = os.path.join(d, safe_name)
    if not os.path.exists(full_path):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    with open(full_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify({'status': 'success', 'brand': brand, 'data': data})


@app.route('/api/<brand_code>/delta-reports/download/<path:filename>')
def brand_download_delta_report(brand_code, filename):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d         = os.path.join('Reports', brand.upper(), 'MasterDelta')
    safe_name = Path(filename).name
    if not os.path.exists(os.path.join(d, safe_name)):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    return send_from_directory(os.path.abspath(d), safe_name, as_attachment=True)


@app.route('/api/<brand_code>/delta-reports/download-latest-xlsx')
def brand_download_latest_delta_xlsx(brand_code):
    brand = _resolve_brand(brand_code)
    if not brand:
        return jsonify({'status': 'error', 'message': f'Unsupported brand: {brand_code}'}), 400
    d          = os.path.join('Reports', brand.upper(), 'MasterDelta')
    xlsx_files = glob.glob(os.path.join(d, 'Master_Delta_Report_*.xlsx'))
    if not xlsx_files:
        return jsonify({'status': 'error', 'message': 'No Excel delta reports found.'}), 404
    latest = max(xlsx_files, key=lambda x: Path(x).stat().st_mtime)
    return send_from_directory(os.path.abspath(d), Path(latest).name, as_attachment=True)


# ── Backward-compatible B1-default routes ────────────────────────────────────

@app.route('/api/validation/live')
def compat_live():                  return brand_live_validation('B1')

@app.route('/api/validation/cached')
def compat_cached():                return brand_cached_validation('B1')

@app.route('/api/validation/latest')
def compat_latest():                return brand_latest_validation('B1')

@app.route('/api/products')
def compat_products():              return brand_products('B1')

@app.route('/api/products/mapped')
def compat_mapped():                return brand_mapped('B1')

@app.route('/api/products/unmapped')
def compat_unmapped():              return brand_unmapped('B1')

@app.route('/api/stats')
def compat_stats():                 return brand_stats('B1')

@app.route('/api/compare/upload', methods=['POST'])
def compat_compare_upload():        return brand_compare_upload('B1')

@app.route('/api/compare/live', methods=['POST'])
def compat_compare_live():          return brand_compare_live('B1')

@app.route('/api/unmapped/live')
def compat_unmapped_live():         return brand_unmapped_live('B1')


# ── CORS proxy ────────────────────────────────────────────────────────────────

@app.route('/api/proxy')
def proxy_get():
    target_url = request.args.get('url', '').strip()
    if not target_url:
        return jsonify({'status': 'error', 'message': 'Missing ?url= parameter'}), 400
    extra_headers = {}
    raw_headers   = request.args.get('headers', '')
    if raw_headers:
        try:
            extra_headers = json.loads(raw_headers)
        except Exception:
            pass
    for k in ['Authorization', 'x-api-key', 'apikey', 'X-Auth-Token']:
        v = request.headers.get(k)
        if v:
            extra_headers[k] = v
    try:
        resp = http_requests.get(target_url, headers=extra_headers, timeout=60, verify=not _INSECURE_TLS)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return jsonify({'status': 'success', 'http_status': resp.status_code,
                        'url': target_url, 'body': body})
    except http_requests.exceptions.ConnectionError as e:
        return jsonify({'status': 'error', 'message': f'Connection failed: {e}'}), 502
    except http_requests.exceptions.Timeout:
        return jsonify({'status': 'error', 'message': 'Timeout (60s)'}), 504
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    resp = make_response(send_from_directory('.', 'index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma']  = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/dashboard/<path:filename>')
def dashboard_files(filename):
    return send_from_directory('.', filename)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    for b in SUPPORTED_BRANDS:
        os.makedirs(_brand_report_dir(b), exist_ok=True)

    print("=" * 80)
    print("  MULTI-BRAND MENU MAPPING VALIDATOR  —  API SERVER")
    print(f"  Supported brands : {', '.join(SUPPORTED_BRANDS)}")
    print("=" * 80)
    print()
    print("  Brand endpoints  (replace <brand> with B1 or B2)")
    print("  ─────────────────────────────────────────────────────")
    print("  GET  /api/<brand>/validation/live")
    print("  GET  /api/<brand>/validation/latest")
    print("  GET  /api/<brand>/products  |  /mapped  |  /unmapped")
    print("  GET  /api/<brand>/stats")
    print("  POST /api/<brand>/compare/upload")
    print("  POST /api/<brand>/compare/live")
    print("  POST /api/<brand>/master-delta/compare/live")
    print("  POST /api/<brand>/master-delta/compare/upload")
    print()
    print("  Utilities")
    print("  ─────────────────────────────────────────────────────")
    print("  GET  /api/brands")
    print("  GET  /api/proxy?url=...")
    print()
    print("  Dashboard : http://localhost:5000/dashboard")
    print()
    print("  Press Ctrl+C to stop")
    print("=" * 80)

    # Bind to localhost and keep the debugger off unless explicitly opted
    # into — Werkzeug's debugger allows arbitrary code execution if reachable.
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(debug=debug, host=host, port=5000, use_reloader=False)
