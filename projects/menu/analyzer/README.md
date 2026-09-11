# Menu Delta Analyzer

A Flask-based web application that compares **PROD vs UAT menu data** for multiple restaurant brands (Brand Two, Brand One, and Brand Three). It fetches menus from live IDP API endpoints or accepts uploaded JSON files, runs 8 structured validation checks, and exports a colour-coded multi-sheet Excel report.

---

## Table of Contents

1. [Overview](#overview)
2. [Supported Brands](#supported-brands)
3. [Getting Started](#getting-started)
4. [How It Works](#how-it-works)
5. [The 8 Validation Checks](#the-8-validation-checks)
6. [Input Modes](#input-modes)
7. [Excel Report Structure](#excel-report-structure)
8. [API Reference](#api-reference)
9. [Project Structure](#project-structure)
10. [Configuration](#configuration)

---

## Overview

The tool answers the question: *"Does the UAT menu match what is on PROD?"*

It pulls menu JSON from the brand's IDP (Intelligent Digital Platform) API for a given PROD store ID, resolves the corresponding UAT store ID (via a configurable store map), then runs a battery of checks covering product counts, ingredient changes, recipe flags, modifier rules, display names, ordering, and presence/absence of products.

---

## Supported Brands

| Brand | Key | PROD API | UAT API |
|---|---|---|---|
| Brand Two | `B2` | `api.brand2.example/menu/{store_id}` | `menu2-b2.staging.staging.example/{store_id}` |
| Brand One | `B1` | `api.brand1.example/menu/{store_id}` | `menu2-b1.uat.staging.example/{store_id}` |
| Brand Three | `B3` | `api.brand3.example/menu/{store_id}` | `menu2-b3.uat.staging.example/{store_id}` |

Pre-configured PROD → UAT store ID mappings are defined for B2 and B1 in `config/brands.json`. Brand Three requires manual UAT store entry.

---

## Getting Started

### Prerequisites

- Python 3.8+
- pip

### Installation & Launch

**Windows (recommended):**

```bat
start.bat
```

This script installs dependencies, creates report directories, opens `http://localhost:5000` in a browser, and starts the server.

**Manual:**

```bash
pip install -r requirements.txt
python app.py
```

Then navigate to `http://localhost:5000`.

---

## How It Works

The pipeline has four stages:

```
User Input (store IDs or JSON files)
        │
        ▼
  1. FETCH  – Retrieve PROD & UAT menu JSON from IDP APIs
        │
        ▼
  2. PARSE  – Normalise raw JSON into indexed, comparison-ready structures
        │
        ▼
  3. COMPARE – Run 8 validation checks across parsed menus
        │
        ▼
  4. REPORT  – Generate a colour-coded multi-sheet Excel file
```

### 1. Fetch (`core/fetcher.py`)

Calls each brand's PROD and UAT endpoints using the appropriate HTTP headers (including `x-channel: WEBOA`, `origin`, and `referer` headers required by the IDP APIs). SSL verification is disabled to handle corporate proxy interception. File uploads bypass the fetch step entirely.

### 2. Parse (`core/parser.py`)

Builds a normalised, indexed structure from the raw IDP JSON. Key design decisions:

- **Products** are indexed four ways:
  - Exact key (e.g. `bun-39b63ffb`)
  - Normalised key — trailing 8-character hex hash stripped (e.g. `bun`)
  - Display-name key — uppercase trimmed name
  - `coreProduct` value from `customAttributes` (most reliable cross-environment identifier)
- **ProductGroups** (modifier/ingredient groups) are indexed by display-name key.
- **Categories** are indexed by display-name key.
- A three-tier algorithm maps every product to its parent categories:
  - Tier 1: Category `childRefs` walk from `rootCategoryRef`
  - Tier 2: Product `groupIds` containing `categories.xxx` references
  - Tier 3: ProductGroup sibling inference for size-variant products

### 3. Compare (`core/comparator.py`)

Orchestrates all 8 checks (see section below) and assembles a unified results dictionary containing per-check findings, a summary (total issues, critical, warnings, new products, removed products), and run metadata.

### 4. Report (`core/report_generator.py`)

Generates a `.xlsx` file using `openpyxl` with:
- A **Summary** sheet with run metadata and per-check pass/fail breakdown
- One worksheet per check, with alternating row colours and status-based cell highlighting
- Brand-coloured title rows (B2 = amber, B1 = red, B3 = blue)
- Colour legend: green = match/OK, yellow = mismatch/warning, orange = new/missing in PROD, red = critical/missing in UAT

Reports are saved to `reports/{BRAND}/` and named `MenuDelta_{BRAND}_PROD{id}_UAT{id}_{timestamp}.xlsx`.

---

## The 8 Validation Checks

### Check 1 – Product Counts by Category (`checks/product_count.py`)

Compares the number of products directly contained in each matching category between PROD and UAT. Flags count mismatches and categories that exist in one environment but not the other.

**Output columns:** Category, PROD Category ID, UAT Category ID, PROD Count, UAT Count, Delta, Status

---

### Check 2 – Ingredient Changes (`checks/ingredients.py`)

For every product group (ingredient set) that exists in both environments, compares the set of child product references. Reports added and removed ingredients, plus count differences.

**Output columns:** PROD Key, UAT Key, Used By, PROD Count, UAT Count, Removed, Status, Added

---

### Check 3 – isRecipe / isDefault Flag Mismatches (`checks/recipe_flags.py`)

Checks whether the `isRecipe` and `isDefault` boolean flags on products and product groups differ between PROD and UAT. Mismatches can affect how items are rendered in the ordering UI.

**Output columns:** Object Type, ID, Name, PROD isRecipe, UAT isRecipe, PROD isDefault, UAT isDefault, Status

---

### Check 4 – Modifier Min/Max Declarations (`checks/modifier_minmax.py`)

Compares `selectionQuantity.min` and `selectionQuantity.max` on product groups and modifier groups. Also compares child counts within each group. Differences here directly impact what a guest can select at order time.

**Output columns:** Object Type, Group, PROD Min, PROD Max, UAT Min, UAT Max, PROD Children, UAT Children, Status

---

### Check 5 – Display Name & Description Changes (`checks/display_names.py`)

Compares the `displayName` and `description` fields for every matched product. Case- and whitespace-normalised comparison to avoid false positives.

**Output columns:** Norm Key, PROD Display Name, UAT Display Name, PROD Description, UAT Description, Status

---

### Check 6 – Modifier Group & Category Ordering (`checks/modifier_ordering.py`)

Checks the **sequence** of items in four areas, each reported on its own sub-sheet:

| Sub-sheet | What is checked |
|---|---|
| A – Category Navigation | Order of sub-categories within top-level categories |
| B – Product List | Order of products within each category |
| C – Product Detail | Order of ingredient refs and modifier group refs on each product |
| D – Group Children | Order of child products within modifier/ingredient groups |

Flags any ordering difference between PROD and UAT, since sequence often drives display order in the app.

---

### Check 7 – Delta Products (`checks/delta_products.py`)

Identifies products that exist in one environment but not the other:

- **New in UAT** — present in UAT, absent in PROD (potential new feature under test)
- **Removed from UAT** — present in PROD, absent in UAT (potential regression)

Matching uses all four product key strategies (exact, normalised, display-name, coreProduct) to minimise false positives caused by environment-specific hash suffixes.

**Output columns:** Product, Product ID, Category, Is Virtual, Is Recipe, Price, Calories, Status, Test Action

---

### Check 8 – Non-Virtual Attributes (`checks/non_virtual.py`)

For every non-virtual, customer-facing product present in both environments, compares three critical attributes:

| Attribute | Severity |
|---|---|
| **Price** | Critical if differs |
| **Availability (`isAvailable`)** | Critical if differs |
| **Calories (`totalCalories`)** | Warning if differs |

An **Overall Status** column rolls up per-product findings. This sheet uses per-column status highlighting so each attribute's health is immediately visible.

**Output columns:** Product, PROD ID, UAT ID, ID Status, PROD Used By, UAT Used By, Object Type, PROD Price, UAT Price, Price Status, PROD Availability, UAT Availability, Availability Status, PROD Calories, UAT Calories, Calorie Status, Overall Status

---

## Input Modes

### Mode 1 – Live API Fetch

Enter a **PROD Store ID** in the UI. The tool auto-resolves the UAT store ID from the configured `store_map` and fetches both menus live.

You may also manually enter a UAT Store ID to override the auto-resolved value.

### Mode 2 – File Upload

Upload pre-saved PROD and UAT menu JSON files. This mode is useful for:
- Offline analysis
- Comparing historical snapshots
- Environments that require VPN or credentials not available in the browser

The upload endpoint accepts `multipart/form-data` with `prod_file` and `uat_file` fields.

---

## Excel Report Structure

| Sheet | Contents |
|---|---|
| **Summary** | Run metadata, totals, per-check pass/fail table |
| **Product Counts** | Category-level product count comparison |
| **Ingredient Changes** | Added/removed ingredients per product group |
| **isRecipe-isDefault Flags** | Boolean flag mismatches |
| **Modifier Min-Max** | Selection quantity rule differences |
| **Display Names** | Name and description changes |
| **Ordering – A Cat Nav** | Category navigation sequence |
| **Ordering – B Product List** | Product ordering within categories |
| **Ordering – C Product Detail** | Per-product ingredient and modifier order |
| **Ordering – D Group Children** | Modifier group child ordering |
| **Delta Products** | Products added to or removed from UAT |
| **Non-Virtual Attributes** | Price, availability, and calorie comparison |

### Status Colour Key

| Colour | Meaning |
|---|---|
| Green | Match / OK / Pass |
| Yellow | Mismatch / Warning |
| Orange | New in UAT / Missing in PROD |
| Red | Critical / Missing in UAT / Removed |

---

## API Reference

All endpoints return JSON.

### `GET /api/brands`
Returns configured brand metadata (names, colours, store maps).

### `POST /api/analyze`
Runs a live-fetch analysis.

**Request body:**
```json
{
  "brand": "B2",
  "prod_store_id": "1000",
  "uat_store_id": "1001"
}
```
`uat_store_id` is optional if a `store_map` entry exists for the PROD store.

**Response:** Summary, per-check issue counts, first 200 findings per check, and a `report_id` for downloading the Excel file.

### `POST /api/upload_analyze`
Runs an analysis from uploaded files. Accepts `multipart/form-data` with fields: `brand`, `prod_store_id` (label), `uat_store_id` (label), `prod_file`, `uat_file`.

### `GET /api/download/{report_id}`
Downloads the generated Excel report as a `.xlsx` file.

### `GET /api/history`
Returns run history grouped by brand (latest 5 runs per brand).

### `POST /api/history`
Saves a history entry. Body must include `brand`.

### `DELETE /api/history?brand={BRAND}`
Clears history for a specific brand, or all history if `brand` is omitted.

---

## Project Structure

```
Menu_Delta_Analyzer/
├── app.py                  # Flask application, routes, and orchestration
├── requirements.txt        # Python dependencies
├── start.bat               # Windows launch script
├── config/
│   └── brands.json         # Brand configurations, API URLs, headers, store maps
├── core/
│   ├── fetcher.py          # HTTP fetch of PROD & UAT menu JSON
│   ├── parser.py           # Normalises raw IDP JSON into indexed structures
│   ├── comparator.py       # Orchestrates all 8 checks
│   ├── report_generator.py # Builds the multi-sheet Excel report
│   └── traversal.py        # Deep product traversal helper
├── checks/
│   ├── product_count.py    # Check 1: Product counts per category
│   ├── ingredients.py      # Check 2: Ingredient set changes
│   ├── recipe_flags.py     # Check 3: isRecipe / isDefault flag mismatches
│   ├── modifier_minmax.py  # Check 4: Min/max selection quantity rules
│   ├── display_names.py    # Check 5: Display name and description changes
│   ├── modifier_ordering.py# Check 6: Ordering of groups and products
│   ├── delta_products.py   # Check 7: Products added or removed
│   └── non_virtual.py      # Check 8: Price, availability, calorie comparison
├── templates/
│   └── index.html          # Single-page web UI
└── reports/
    ├── history.json        # Persisted run history
    ├── B2/                # B2 Excel reports
    ├── B1/                # B1 Excel reports
    └── B3/                # B3 Excel reports
```

---

## Configuration

`config/brands.json` controls everything brand-specific:

| Field | Description |
|---|---|
| `name` | Full brand name |
| `short` | Short code used in filenames |
| `color` | Hex colour for UI and report title rows |
| `logo_char` | Emoji displayed in the UI |
| `prod_url` | PROD API URL template (`{store_id}` is substituted) |
| `uat_url` | UAT API URL template |
| `prod_headers` | HTTP headers for PROD API requests |
| `uat_headers` | HTTP headers for UAT API requests |
| `store_map` | `{ "PROD_store_id": "UAT_store_id" }` — auto-resolves UAT ID |

To add a new store mapping for B2 without restarting the server, edit `config/brands.json` — the app re-reads it on every request.
