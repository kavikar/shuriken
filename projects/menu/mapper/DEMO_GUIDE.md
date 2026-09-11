# 🍔🍗 Multi-Brand Menu Mapping Validator — Demo Guide

> **Version:** 2.0 &nbsp;|&nbsp; **Supported Brands:** Brand One (B1) · Brand Two (B2)  
> **Last Updated:** March 2026

---

## 📌 What Is This Tool?

The **Multi-Brand Menu Mapping Validator** is an internal web dashboard that automates the validation of POS product ID mappings between a **Location Menu** and the **Master Menu** on the MenuApi platform.

It also provides a **UAT vs PROD Master Delta** comparison to identify any discrepancies between the two environments before a release.

---

## 🚀 How to Launch

### Step 1 — Start the Server
Double-click **`start_server.bat`** located in the `Multi_Brand_Menu_Mapping_Validator` folder.

```
📁 Multi_Brand_Menu_Mapping_Validator/
   └── start_server.bat  ← Double-click this
```

- The Flask server starts silently in the background (no CMD window needed).
- Your browser automatically opens the dashboard at **http://127.0.0.1:5000/**.

### Step 2 — Stop the Server
Run this command in any PowerShell or CMD window:
```
taskkill /f /im python.exe
```

> ✅ The server runs independently — closing VS Code or any terminal does **not** stop it.

---

## 🖥️ Dashboard Overview

The dashboard has **two main tabs**:

| Tab | Purpose |
|---|---|
| 🔗 **Location vs Master** | Validate POS mapping for a specific store location against the Master Menu |
| 🔄 **UAT vs PROD Delta** | Compare Master Menu mappings between UAT and PROD environments |

Each tab has two sub-modes:
- **⚡ Live cURL** — paste a cURL command to fetch live data from MenuApi API
- **📤 Upload & Compare** — upload saved JSON files for offline comparison

---

## 🔗 Tab 1 — Location vs Master

### What it does
Compares every product in a **store's location menu** against the **Master Menu mapping lookup** and flags:
- ✅ **Mapped** — product has a valid `posId` in the master
- ❌ **Unmapped** — product is missing from the master or has no `posId`

### Deep Analysis Includes
The engine inspects all nested menu structures:
- Main `products`
- `productGroups` → `childRefs`
- `ingredientRefs`
- `alternatives`
- `modifierGroupRefs`

### How to Use — Live cURL Mode

1. Select brand: **B1** or **B2**
2. Click **⚡ Live cURL** sub-tab
3. The Location cURL and Master cURL fields are **pre-filled** with sample commands
4. Optionally replace the `location_id` in the Location cURL with any store ID
5. Click **▶ Run Validation**

**Sample Location cURL (B1):**
```bash
curl --location 'https://menu-api.example/api/v1/menu_events/data
  ?location_id=1000&brand=B1&event_type=menu' \
  --header 'Authorization: Bearer <token>'
```

### How to Use — Upload Mode

1. Select brand
2. Click **📤 Upload & Compare** sub-tab
3. Upload:
   - **Location Menu JSON** — from a specific store (e.g. store 1000)
   - **Master Menu JSON** — the master mapping lookup file
4. Click **Compare**

---

## 🔄 Tab 2 — UAT vs PROD Delta

### What it does
Fetches the **Master Menu** from both **UAT** and **PROD** environments and produces a side-by-side delta report with four statuses:

| Status | Meaning |
|---|---|
| 🟡 **UAT Only** | Key exists in UAT master but is **missing** from PROD |
| 🔴 **PROD Only** | Key exists in PROD master but is **missing** from UAT |
| 🟠 **Modified** | Key exists in both but one or more field values differ |
| 🟢 **Matched** | Key exists in both with **identical** field values |

### Fields Compared

**B1:** `posId`, `menuItemId`, `optionGroupId`, `drinkComponentId`, `entreeComponentId`, `sideComponentId`

**B2:** `posId`, `salesItemId`, `optionGroupId`, `menuItemId`

### How to Use — Live cURL Mode

1. Select brand: **B1** or **B2**
2. Click **⚡ Live cURL** sub-tab
3. UAT and PROD cURL commands are **pre-filled**
4. Click **▶ Run Delta**

### How to Use — Upload Mode

1. Select brand
2. Click **📤 Upload Files** sub-tab
3. Upload:
   - **UAT Master JSON**
   - **PROD Master JSON**
4. Click **Compare**

---

## 📊 Reading the Results

### Location vs Master Results
After running validation you'll see:

- **Summary cards** — Total products, Mapped %, Unmapped count
- **Filtered views** — All / Mapped Only / Unmapped Only
- **Detail table** — Product ID, Display Name, Category, `posId`, extra mapping fields, mapping type

### UAT vs PROD Delta Results
After running the delta you'll see:

- **Summary cards** — counts per delta status (UAT Only / PROD Only / Modified / Matched)
- **Filter buttons** — filter table by status
- **Detail table** — Product Key, Status, UAT value, PROD value, Field Differences

> 💡 The **Modified** rows show exactly which fields changed and the old → new values side by side.

---

## 🌐 Supported Brands

| Brand | Code | Default Store | Primary Mapping Field |
|---|---|---|---|
| Brand One | `B1` | 1000 | `posId` |
| Brand Two | `B2` | 5 | `posId` |

---

## 🔧 API Endpoints (for developers)

The tool exposes a REST API at `http://127.0.0.1:5000`:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/brands` | List all brand configs |
| GET | `/api/<brand>/validation/live` | Run live validation |
| GET | `/api/<brand>/validation/latest` | Latest saved report |
| GET | `/api/<brand>/stats` | Summary statistics |
| POST | `/api/<brand>/compare/upload` | Upload files & compare |
| POST | `/api/<brand>/compare/live` | Live cURL compare |
| POST | `/api/<brand>/master-delta/live` | Live UAT vs PROD delta |
| POST | `/api/<brand>/master-delta/upload` | Upload & delta compare |

Replace `<brand>` with `B1` or `B2`.

---

## 📁 Project Structure

```
Multi_Brand_Menu_Mapping_Validator/
├── api_server.py          # Flask REST API + dashboard server
├── validator_engine.py    # Core mapping validation logic
├── master_delta_engine.py # UAT vs PROD delta comparison engine
├── brand_config.py        # Per-brand settings (tokens, URLs, fields)
├── index.html             # Web dashboard (single-page app)
├── start_server.bat       # One-click server launcher
├── requirements.txt       # Python dependencies
└── Reports/
    ├── B1/               # Saved B1 validation reports (JSON)
    └── B2/               # Saved B2 validation reports (JSON)
```

---

## ⚙️ Requirements

- Python 3.9+
- Install dependencies once:
  ```
  pip install -r requirements.txt
  ```
- Dependencies: `flask`, `flask-cors`, `pandas`, `requests`, `openpyxl`

---

## ❓ FAQ

**Q: The browser shows a JSON response instead of the dashboard.**  
A: Navigate to `http://127.0.0.1:5000/dashboard` directly.

**Q: The page doesn't load after double-clicking the bat.**  
A: Wait 3–4 seconds for the server to start, then refresh the browser.

**Q: How do I add a new brand?**  
A: Add a new `BrandConfig` entry in `brand_config.py` following the B1/B2 pattern, then register it in `BRAND_CONFIGS`.

**Q: Where are validation reports saved?**  
A: Auto-saved as JSON files under `Reports/B1/` or `Reports/B2/` after each live validation run.
