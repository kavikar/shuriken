"""
Fetcher: Retrieves PROD and UAT menu JSON from IDP APIs or from uploaded file data.
"""

import os
import warnings
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from typing import Tuple, Optional

# Corporate-proxy escape hatch: TLS verification is on by default and only
# disabled when explicitly opted into, rather than always skipped.
_INSECURE_TLS = os.environ.get("ALLOW_INSECURE_TLS") == "1"
if _INSECURE_TLS:
    # Suppress SSL warnings only when verification is actually off.
    warnings.filterwarnings("ignore", category=InsecureRequestWarning)


def fetch_menu(url: str, headers: dict, timeout: int = 30) -> dict:
    """Fetch menu data from the given URL with the provided headers."""
    resp = requests.get(url, headers=headers, timeout=timeout, verify=not _INSECURE_TLS)
    resp.raise_for_status()
    return resp.json()


def fetch_prod_and_uat(
    brand_cfg: dict,
    prod_store_id: str,
    uat_store_id: str,
    prod_override: Optional[dict] = None,
    uat_override: Optional[dict] = None,
) -> Tuple[dict, dict, str, str]:
    """
    Fetch PROD and UAT menus.
    If override dicts are provided (from file upload), use those instead of live fetch.
    Returns (prod_data, uat_data, prod_url_used, uat_url_used)
    """
    prod_url = brand_cfg["prod_url"].format(store_id=prod_store_id)
    uat_url = brand_cfg["uat_url"].format(store_id=uat_store_id)

    if prod_override is not None:
        prod_data = prod_override
        prod_url = f"[Uploaded JSON – PROD Store {prod_store_id}]"
    else:
        prod_data = fetch_menu(prod_url, brand_cfg["prod_headers"])

    if uat_override is not None:
        uat_data = uat_override
        uat_url = f"[Uploaded JSON – UAT Store {uat_store_id}]"
    else:
        uat_data = fetch_menu(uat_url, brand_cfg["uat_headers"])

    return prod_data, uat_data, prod_url, uat_url
