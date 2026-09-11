"""
Report Generator: Creates a multi-worksheet Excel report from comparison results.

Worksheets:
  1  Summary
  2  Product Counts by Category
  3  Ingredient Changes
  4  isRecipe Flag Mismatches
  5  Modifier Min/Max Declarations
  6  Display Name & Description Changes
  7  Modifier Group Ordering
  8  Delta Products
  9  Non-Virtual Attributes  ← highlighted separately per spec
"""

import os
from datetime import datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import (
    PatternFill, Font, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.styles.numbers import FORMAT_PERCENTAGE

# ── Colour palette ─────────────────────────────────────────────────────────
C_RED        = "FFDC143C"   # Critical / error
C_ORANGE     = "FFFF8C00"   # Warning
C_GREEN      = "FF228B22"   # OK / match
C_YELLOW     = "FFFFD700"   # Mismatch
C_BLUE_HDR   = "FF1F3864"   # Header background (dark navy)
C_BLUE_LIGHT = "FFD6E4F0"   # Alternating row light
C_WHITE      = "FFFFFFFF"
C_GREY       = "FFF2F2F2"
C_BRAND_B2   = "FFFFB300"
C_BRAND_B1   = "FFE31837"
C_BRAND_B3   = "FF0055A5"
C_TITLE_BG   = "FF2C3E50"

BRAND_COLORS = {
    "B2": C_BRAND_B2,
    "B1": C_BRAND_B1,
    "B3": C_BRAND_B3,
}

# ── Status → fill colour ────────────────────────────────────────────────────
STATUS_FILLS = {
    "MATCH":                PatternFill("solid", fgColor=C_GREEN),
    "OK":                   PatternFill("solid", fgColor=C_GREEN),
    "MISMATCH":             PatternFill("solid", fgColor=C_YELLOW),
    "COUNT MISMATCH":       PatternFill("solid", fgColor=C_YELLOW),
    "CHANGED":              PatternFill("solid", fgColor=C_YELLOW),
    "MISSING IN UAT":       PatternFill("solid", fgColor=C_RED),
    "MISSING IN PROD":      PatternFill("solid", fgColor=C_ORANGE),
    "NEW IN UAT":           PatternFill("solid", fgColor=C_ORANGE),
    "REMOVED FROM UAT":     PatternFill("solid", fgColor=C_RED),
    "CRITICAL":             PatternFill("solid", fgColor=C_RED),
    "WARNING":              PatternFill("solid", fgColor=C_YELLOW),
    "N/A (NEW)":            PatternFill("solid", fgColor=C_ORANGE),
    "N/A (REMOVED)":        PatternFill("solid", fgColor=C_RED),
}

WHITE_FONT   = Font(color=C_WHITE, bold=True)
DARK_FONT    = Font(color="FF1A1A1A")
HDR_FONT     = Font(color=C_WHITE, bold=True, size=10)
TITLE_FONT   = Font(color=C_WHITE, bold=True, size=13)

THIN = Side(style="thin", color="FFAAAAAA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT   = Alignment(horizontal="left",   vertical="center", wrap_text=True)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _apply_header(ws, columns: list, row: int = 1):
    hdr_fill = PatternFill("solid", fgColor=C_BLUE_HDR)
    for col, title in enumerate(columns, 1):
        cell = ws.cell(row=row, column=col, value=title)
        cell.fill = hdr_fill
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _auto_col_width(ws, min_width=12, max_width=50):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 2, max_width))


def _freeze(ws, cell="A2"):
    ws.freeze_panes = cell


def _status_fill(status: str):
    for key, fill in STATUS_FILLS.items():
        if key in str(status).upper():
            return fill
    return None


def _write_title_row(ws, title: str, brand: str, cols: int):
    brand_color = BRAND_COLORS.get(brand, C_TITLE_BG)
    title_fill = PatternFill("solid", fgColor=C_TITLE_BG)
    brand_fill = PatternFill("solid", fgColor=brand_color)

    ws.row_dimensions[1].height = 28
    for c in range(1, cols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = title_fill
        cell.font = TITLE_FONT
        cell.alignment = CENTER
    ws.cell(row=1, column=1, value=title)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=cols)


def _write_findings(ws, findings: list, columns: list, data_keys: list,
                    start_row: int = 3, status_key: str = "status"):
    for r_idx, row in enumerate(findings):
        excel_row = start_row + r_idx
        fill_even = PatternFill("solid", fgColor=C_BLUE_LIGHT)
        fill_odd  = PatternFill("solid", fgColor=C_WHITE)

        for c_idx, dk in enumerate(data_keys, 1):
            val = row.get(dk, "")
            cell = ws.cell(row=excel_row, column=c_idx, value=_cell_val(val))
            cell.alignment = LEFT
            cell.border = BORDER
            cell.fill = fill_even if r_idx % 2 == 0 else fill_odd

        # Colour the status column
        st = row.get(status_key, "")
        status_col = None
        try:
            status_col = data_keys.index(status_key) + 1
        except ValueError:
            pass
        if status_col:
            status_cell = ws.cell(row=excel_row, column=status_col)
            fill = _status_fill(str(st))
            if fill:
                status_cell.fill = fill
                status_cell.font = Font(bold=True,
                                        color=C_WHITE if str(st).upper() in
                                        {"MATCH", "OK", "MISSING IN UAT",
                                         "REMOVED FROM UAT", "CRITICAL",
                                         "BOTH MISSING"} else "FF1A1A1A")


def _cell_val(val: Any) -> Any:
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if isinstance(val, set):
        return ", ".join(sorted(val)) or "—"
    if isinstance(val, list):
        if not val:
            return "—"
        # Grouped ingredient format: [{group, items}, ...]
        if isinstance(val[0], dict) and "group" in val[0]:
            return " | ".join(
                f"{g['group']}: {', '.join(g['items'])}" for g in val
            )
        return ", ".join(str(v) for v in val)
    if val is None:
        return "—"
    return val


# ── Summary sheet ────────────────────────────────────────────────────────────

def _write_summary(wb: Workbook, results: dict, brand: str):
    ws = wb.create_sheet("Summary", 0)
    ws.sheet_view.showGridLines = False

    meta = results["meta"]
    summary = results["summary"]
    checks = results["checks"]

    brand_color = BRAND_COLORS.get(brand, C_TITLE_BG)
    fill_hdr = PatternFill("solid", fgColor=brand_color)
    fill_dark = PatternFill("solid", fgColor=C_TITLE_BG)

    # Title block
    ws.row_dimensions[1].height = 36
    ws.row_dimensions[2].height = 20
    for c in range(1, 6):
        ws.cell(row=1, column=c).fill = fill_dark
        ws.cell(row=2, column=c).fill = fill_dark

    ws.merge_cells("A1:E1")
    title_cell = ws.cell(row=1, column=1, value="🍔  Menu Delta Analyzer – Comparison Report")
    title_cell.font = Font(bold=True, size=16, color=C_WHITE)
    title_cell.alignment = CENTER

    ws.merge_cells("A2:E2")
    subtitle = ws.cell(row=2, column=1,
                       value=f"{meta.get('brand','')}  |  "
                             f"PROD Store: {meta.get('prod_store','')}  |  "
                             f"UAT Store: {meta.get('uat_store','')}  |  "
                             f"Generated: {meta.get('timestamp','')}")
    subtitle.font = Font(size=10, color="FFCCCCCC")
    subtitle.alignment = CENTER

    # Meta table
    row = 4
    labels = [
        ("Brand",              meta.get("brand", "")),
        ("PROD Store ID",      meta.get("prod_store", "")),
        ("UAT Store ID",       meta.get("uat_store", "")),
        ("PROD Menu Name",     meta.get("prod_menu_name", "")),
        ("UAT Menu Name",      meta.get("uat_menu_name", "")),
        ("PROD URL",           meta.get("prod_url", "")),
        ("UAT URL",            meta.get("uat_url", "")),
        ("PROD Total Products",meta.get("prod_product_count", 0)),
        ("UAT Total Products", meta.get("uat_product_count", 0)),
        ("PROD Modifier Groups",meta.get("prod_group_count", 0)),
        ("UAT Modifier Groups", meta.get("uat_group_count", 0)),
        ("Analysis Timestamp", meta.get("timestamp", "")),
    ]
    for label, value in labels:
        lc = ws.cell(row=row, column=1, value=label)
        lc.font = Font(bold=True)
        lc.fill = PatternFill("solid", fgColor=C_GREY)
        lc.border = BORDER
        lc.alignment = LEFT
        vc = ws.cell(row=row, column=2, value=str(value))
        vc.border = BORDER
        vc.alignment = LEFT
        row += 1

    # Summary stats
    row += 1
    ws.cell(row=row, column=1, value="SUMMARY").font = Font(bold=True, size=12)
    row += 1

    stat_labels = [
        ("Total Issues Found",  summary["total_issues"],  C_ORANGE if summary["total_issues"] else C_GREEN),
        ("Critical Issues",     summary["critical"],       C_RED if summary["critical"] else C_GREEN),
        ("Warnings",            summary["warnings"],       C_YELLOW if summary["warnings"] else C_GREEN),
        ("New Products in UAT", summary["new_products"],   C_ORANGE if summary["new_products"] else C_GREEN),
        ("Removed from UAT",    summary["removed_products"],C_RED if summary["removed_products"] else C_GREEN),
    ]
    for label, value, color in stat_labels:
        lc = ws.cell(row=row, column=1, value=label)
        lc.font = Font(bold=True)
        lc.border = BORDER
        lc.fill = PatternFill("solid", fgColor=C_GREY)
        vc = ws.cell(row=row, column=2, value=value)
        vc.fill = PatternFill("solid", fgColor=color)
        vc.font = Font(bold=True, color=C_WHITE)
        vc.border = BORDER
        vc.alignment = CENTER
        row += 1

    # Per-check breakdown
    row += 1
    ws.cell(row=row, column=1, value="CHECK BREAKDOWN").font = Font(bold=True, size=12)
    row += 1

    check_hdr = ["Check Name", "Total Items", "Issues Found", "Status"]
    _apply_header(ws, check_hdr, row=row)
    row += 1

    check_labels = {
        "product_count":     "1. Product Counts by Category",
        "ingredients":       "2. Ingredient Changes",
        "recipe_flags":      "3. isRecipe Flag Mismatches",
        "modifier_minmax":   "4. Modifier Min/Max Declarations",
        "display_names":     "5. Display Name & Description",
        "modifier_ordering": "6. Modifier Group & Category Ordering",
        "delta_products":    "7. Delta Products",
        "non_virtual":       "8. Non-Virtual Attributes",
    }

    for ck, label in check_labels.items():
        c = checks.get(ck, {})
        issues = c.get("issues", 0)
        total  = c.get("total", 0)
        status = "PASS ✅" if issues == 0 else f"FAIL ❌ ({issues} issues)"
        fill = PatternFill("solid", fgColor=C_GREEN if issues == 0 else C_RED)
        font = Font(bold=True, color=C_WHITE)

        ws.cell(row=row, column=1, value=label).border = BORDER
        ws.cell(row=row, column=2, value=total).border = BORDER
        ws.cell(row=row, column=3, value=issues).border = BORDER
        st_cell = ws.cell(row=row, column=4, value=status)
        st_cell.fill = fill
        st_cell.font = font
        st_cell.border = BORDER
        st_cell.alignment = CENTER
        row += 1

    # Column widths
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 24
    ws.column_dimensions["E"].width = 16


# ── Generic worksheet writer ─────────────────────────────────────────────────

def _write_check_sheet(wb: Workbook, check_result: dict, brand: str,
                       sheet_name: str, data_keys: list, status_key: str = "status"):
    ws = wb.create_sheet(sheet_name)
    ws.sheet_view.showGridLines = False

    findings = check_result.get("findings", [])
    # Derive columns from findings keys if not explicitly provided
    if "columns" in check_result:
        cols = check_result["columns"]
    elif findings:
        cols = [k.replace('_', ' ').title() for k in findings[0].keys()]
    else:
        cols = data_keys

    _write_title_row(ws, check_result["title"], brand, len(cols))
    _apply_header(ws, cols, row=2)
    ws.row_dimensions[2].height = 22
    _freeze(ws, "A3")

    _write_findings(ws, findings, cols, data_keys, start_row=3, status_key=status_key)
    _auto_col_width(ws)


# ── Non-virtual sheet (special multi-status highlight) ───────────────────────

def _write_non_virtual_sheet(wb: Workbook, check_result: dict, brand: str):
    ws = wb.create_sheet("Non-Virtual Attributes")
    ws.sheet_view.showGridLines = False

    cols = check_result["columns"]
    findings = check_result.get("findings", [])

    _write_title_row(ws, check_result["title"], brand, len(cols))
    _apply_header(ws, cols, row=2)
    ws.row_dimensions[2].height = 22
    _freeze(ws, "A3")

    # Status columns indices (0-based in cols list)
    PRICE_ST_COL  = cols.index("Price Status") + 1
    AVAIL_ST_COL  = cols.index("Availability Status") + 1
    CAL_ST_COL    = cols.index("Calorie Status") + 1
    OVERALL_COL   = cols.index("Overall Status") + 1

    data_keys = [
        "product", "prod_id", "uat_id", "id_status",
        "prod_used_by", "uat_used_by", "object_type",
        "prod_price", "uat_price", "price_status",
        "prod_availability", "uat_availability", "availability_status",
        "prod_calories", "uat_calories", "calories_status",
        "overall_status",
    ]

    for r_idx, row in enumerate(findings):
        excel_row = 3 + r_idx
        fill_base = PatternFill("solid", fgColor=C_BLUE_LIGHT if r_idx % 2 == 0 else C_WHITE)

        for c_idx, dk in enumerate(data_keys, 1):
            val = row.get(dk, "—")
            cell = ws.cell(row=excel_row, column=c_idx, value=_cell_val(val))
            cell.alignment = LEFT
            cell.border = BORDER
            cell.fill = fill_base

        # Per-status column colouring
        for st_col, dk in [(PRICE_ST_COL, "price_status"),
                           (AVAIL_ST_COL, "availability_status"),
                           (CAL_ST_COL,   "calories_status"),
                           (OVERALL_COL,  "overall_status")]:
            st = str(row.get(dk, ""))
            fill = _status_fill(st)
            cell = ws.cell(row=excel_row, column=st_col)
            if fill:
                cell.fill = fill
                cell.font = Font(
                    bold=True,
                    color=C_WHITE if st.upper() in {
                        "MATCH", "OK", "MISSING IN UAT", "REMOVED FROM UAT",
                        "CRITICAL"
                    } else "FF1A1A1A",
                )

    _auto_col_width(ws)


# ── Master entry point ────────────────────────────────────────────────────────

def generate(results: dict, output_dir: str) -> str:
    """
    Generate the Excel report and return the file path.
    """
    meta   = results["meta"]
    brand  = meta.get("brand", "UNKNOWN")
    checks = results["checks"]

    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"MenuDelta_{brand}_PROD{meta.get('prod_store','')}_UAT{meta.get('uat_store','')}_{ts}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb = Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # 1. Summary
    _write_summary(wb, results, brand)

    # 2. Product Counts
    _write_check_sheet(wb, checks["product_count"], brand,
                       "Product Counts",
                       ["category", "prod_cat_id", "uat_cat_id", "prod_count", "uat_count", "delta", "status"])

    # 3. Ingredient Changes
    _write_check_sheet(wb, checks["ingredients"], brand,
                       "Ingredient Changes",
                       ["prod_key", "uat_key", "used_by", "prod_count", "uat_count", "removed", "status", "added"])

    # 4. isRecipe / isDefault Flags
    _write_check_sheet(wb, checks["recipe_flags"], brand,
                       "isRecipe-isDefault Flags",
                       ["object_type", "id", "name", "prod_isRecipe", "uat_isRecipe",
                        "prod_isDefault", "uat_isDefault", "status"])

    # 5. Modifier Min/Max
    _write_check_sheet(wb, checks["modifier_minmax"], brand,
                       "Modifier Min-Max",
                       ["object_type", "group", "prod_min", "prod_max", "uat_min", "uat_max",
                        "prod_children", "uat_children", "status"])

    # 6. Display Names
    _write_check_sheet(wb, checks["display_names"], brand,
                       "Display Names",
                       ["norm_key", "prod_display_name", "uat_display_name",
                        "prod_description", "uat_description", "status"])

    # 7. Ordering / Sequence – 4 sub-sheets
    _mo = checks["modifier_ordering"]
    _mo_sub = _mo.get("sub_checks", [])

    def _mo_sheet(idx, sheet_name, data_keys):
        if idx < len(_mo_sub):
            sc = _mo_sub[idx]
            # build a minimal check_result compatible with _write_check_sheet
            fake = {
                "title":    f"{_mo['title']}  ·  {sc['subtitle']}",
                "columns":  [k.replace("_", " ").title() for k in data_keys],
                "findings": sc.get("findings", []),
            }
            _write_check_sheet(wb, fake, brand, sheet_name, data_keys)

    _mo_sheet(0, "Ordering – A Cat Nav",
              ["parent_category", "prod_count", "uat_count",
               "prod_order", "uat_order", "diff_summary", "status"])

    _mo_sheet(1, "Ordering – B Product List",
              ["category", "prod_count", "uat_count",
               "prod_order", "uat_order", "diff_summary", "status"])

    _mo_sheet(2, "Ordering – C Product Detail",
              ["product_id", "prod_ing_order", "uat_ing_order",
               "prod_mod_order", "uat_mod_order", "ing_diff", "mod_diff", "status"])

    _mo_sheet(3, "Ordering \u2013 D Group Children",
              ["group_name", "prod_group_id", "uat_group_id", "used_by",
               "prod_count", "uat_count", "prod_order", "uat_order", "diff_summary", "status"])

    # 8. Delta Products
    _write_check_sheet(wb, checks["delta_products"], brand,
                       "Delta Products",
                       ["product", "product_id", "category", "is_virtual", "is_recipe",
                        "price", "calories", "status", "test_action"])

    # 9. Non-Virtual Attributes (dedicated writer)
    _write_non_virtual_sheet(wb, checks["non_virtual"], brand)

    wb.save(filepath)
    return filepath
