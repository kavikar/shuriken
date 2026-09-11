# Multi-Brand Menu Mapping Validator

Validates product ID mappings between **Location Menu** and **Master Menu** files for multiple brands, with full Excel/JSON export, REST API, and interactive web dashboard with brand switching.

Currently supported brands:
- 🍔 **B1** (Brand One)
- 🍗 **B2** (Brand Two)

---

## 📁 Folder Structure

```
Multi_Brand_Menu_Mapping_Validator/
├── brand_config.py          ← Brand-specific configurations (API, colours, fields)
├── validator_engine.py      ← Core validation engine (brand-agnostic)
├── api_server.py            ← Flask REST API server (multi-brand routes)
├── index.html               ← Web dashboard with brand switcher
├── requirements.txt         ← Python dependencies
├── README.md                ← This file
└── Reports/
    ├── B1/                 ← Brand One reports (Excel + JSON)
    └── B2/                 ← B2 reports (Excel + JSON)
```

> **Note:** The original `B1_Master_Menu_Mapping/` folder is fully preserved and untouched.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Validation (CLI)
```bash
# Brand One
python validator_engine.py B1

# Brand Two
python validator_engine.py B2
```

### 3. Start API Server
```bash
python api_server.py
```

### 4. Open Dashboard
```
http://localhost:5000/dashboard
```

Use the brand toggle at the top to switch between 🍔 B1 and 🍗 B2.

---

## 📊 Excel Report (8 Sheets)

| # | Sheet | Description |
|---|-------|-------------|
| 1 | All Products | Complete list with all mapping details |
| 2 | Non-Virtual Products | Excluding virtual products |
| 3 | Mapped Products | Products with valid POS mappings |
| 4 | Unmapped Products | Products missing POS mappings |
| 5 | Products in Groups | Products referenced in productGroups |
| 6 | Summary | Statistical overview |
| 7 | Contextual Mappings | All `parent#child` path entries from mappingLookup |
| 8 | Root Cause Analysis | Why each unmapped product is missing + recommended action |

---

## 📡 API Endpoints

### Brand-Specific (replace `<brand>` with `B1` or `B2`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/<brand>/validation/live` | Run live validation (fresh results) |
| GET | `/api/<brand>/validation/latest` | Load most recent JSON from Reports/ |
| GET | `/api/<brand>/validation/cached` | Return in-memory cached data |
| GET | `/api/<brand>/products` | All products |
| GET | `/api/<brand>/products/mapped` | Mapped products only |
| GET | `/api/<brand>/products/unmapped` | Unmapped products only |
| GET | `/api/<brand>/stats` | Summary statistics |
| POST | `/api/<brand>/compare/upload` | Upload location + master files |
| POST | `/api/<brand>/compare/live` | Live cURL compare (JSON body) |

### Utility Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/brands` | List all brand configs |
| GET | `/api/proxy?url=…` | CORS proxy for external APIs |
| GET | `/dashboard` | Web dashboard UI |

### Backward Compatible (defaults to B1)

| Old Route | Maps To |
|-----------|---------|
| `/api/validation/live` | `/api/B1/validation/live` |
| `/api/stats` | `/api/B1/stats` |
| `/api/products` | `/api/B1/products` |

### Example API Calls
```bash
# B2 live validation
curl http://localhost:5000/api/B2/validation/live

# B1 stats
curl http://localhost:5000/api/B1/stats

# B2 unmapped products
curl http://localhost:5000/api/B2/products/unmapped

# Live cURL compare for B2
curl -X POST http://localhost:5000/api/B2/compare/live \
  -H "Content-Type: application/json" \
  -d '{
    "uat_url": "https://menu-api.example/api/v1/menu_events/data?location_id=5&brand=B2&event_type=menu",
    "uat_headers": {"Authorization": "Bearer REPLACE_ME_TOKEN"},
    "master_url": "https://menu-api.example/api/v1/menu_events/data?location_id=master&brand=B2&event_type=menu",
    "master_headers": {"Authorization": "Bearer REPLACE_ME_TOKEN"}
  }'
```

---

## 🔑 Key Differences Between Brands

| Aspect | B1 | B2 |
|--------|-----|-----|
| Primary mapping check | `posId` | `posId` |
| Extra mapping fields | `menuItemId`, `optionGroupId`, `drinkComponentId`, `entreeComponentId`, `sideComponentId` | `salesItemId`, `optionGroupId`, `menuItemId` |
| Master file format | Full MenuApi JSON response | JSON fragment (`"mappingLookup": {…}`) |
| Contextual entries | ~394 | ~4,690 |
| Total mapping entries | ~706 | ~8,371 |
| Dashboard theme | 🔴 Red gradient | ⬛ Black + 🟡 Gold |

---

## 🔍 Validation Logic

Products are extracted from **5 sources** in the location menu:
1. `main_products`
2. `productGroups` → `childRefs`
3. `ingredientRefs`
4. `alternatives`
5. `modifierGroupRefs`

Each product is checked against two mapping types:

| Type | Logic |
|------|-------|
| **Direct** | `mappingLookup[productId].posId` exists |
| **Contextual** | `mappingLookup["parentId#productId"]` exists |

---

## 🌐 Dashboard Features

- **Brand switcher** — Toggle between B1 🍔 and B2 🍗
- **Dynamic theming** — Colours, gradients, table headers adapt per brand
- **Brand-specific columns** — Shows `Sales Item ID` for B2, `Menu Item ID` for B1
- **Pre-filled curl commands** — Each brand auto-populates API URLs
- **2 load options** — 📤 Upload & Compare · 🔗 Live cURL Compare
- Clickable stat cards (Total / Mapped / Unmapped / Virtual / Contextual)
- Search by product name or ID
- Filter by status, source, recipe, default
- 🔄 Refresh resets all filters

---

## 🛠 Troubleshooting

**Port 5000 already in use:**
```bash
netstat -ano | findstr :5000
```

**Dashboard shows "No Data":**
1. Ensure `python api_server.py` is running
2. Use the Live cURL tab with pre-filled commands
3. Check browser console (F12) for errors

**Missing dependencies:**
```bash
pip install flask flask-cors pandas openpyxl requests
```
