"""Create data/raw/manual/manual_price_entry.xlsx: the workbook for recording
room and studio listings by hand while browsing. No scraping: every row is
typed in by a person.

Sheets:
    Rooms     area, room_type, price, building, source_site, date_seen, url
    Studios   area, price, building, source_site, date_seen, url
    Progress  one row per target cell; formulas, so it updates as you type
    Lists     (hidden) canonical areas, room types, source sites, and the
              buildings each target cell already has in the database

The fixed "DB" numbers come from data/processed/baseline_listings.csv (the
build the database was seeded from), counting every source except manual —
manual rows are this workbook's own. Re-run after a rebuild to refresh them.

Usage:
    nlp-service/.venv/Scripts/python -m scripts.baseline.manual_workbook [--force]

It refuses to overwrite an existing workbook unless --force: the file holds
your entries.
"""
import argparse
import json
import os
import sys
from datetime import date

import pandas as pd
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.scrapers import config  # noqa: E402

from scripts.baseline.cleaning import PRICE_MAX, WHOLE_UNIT_MIN_PRICE  # noqa: E402
from scripts.baseline.schema import MIN_BUILDINGS, MIN_LISTINGS, building_key  # noqa: E402

OUT = os.path.join(config.ROOT, "data", "raw", "manual", "manual_price_entry.xlsx")
LISTINGS = os.path.join(config.DATA_PROCESSED, "baseline_listings.csv")
COVERAGE = os.path.join(config.DATA_PROCESSED, "external_coverage.json")

# DECISION (author, 2026-10-19) — the lowest price each sheet accepts. The spec
# said 50, but anything under these is never a usable row: the build drops a
# whole unit under RM300 as a per-day price (cleaning.WHOLE_UNIT_MIN_PRICE),
# and a room under RM150 is below the minimum-rent floor (backend
# price.service.js RENT_FLOOR.room), so it would count in Progress and then
# contradict the scoring. Keep in step with RENT_FLOOR.
STUDIO_MIN_PRICE = WHOLE_UNIT_MIN_PRICE   # 300
ROOM_MIN_PRICE = 150

SOURCE_SITES = ["iProperty", "PropertyGuru", "Mudah", "iBilik", "Speedhome", "Facebook", "other"]
ROOM_TYPES = ["master", "common"]

# The Progress rows, in the order the user set (2026-10-19): common rooms,
# then studios, then master rooms (later). Studios only where the cell is not
# scorable yet.
SEVEN = ["Setapak", "Cheras (KL)", "Seri Kembangan", "Puchong (Selangor)", "Shah Alam",
         "Petaling Jaya", "Subang Jaya"]
STUDIO_AREAS = ["Setapak", "Cheras (KL)", "Puchong (Selangor)", "Subang Jaya"]
TARGETS = ([("1", area, "common") for area in SEVEN]
           + [("2", area, "studio") for area in STUDIO_AREAS]
           + [("3 (later)", area, "master") for area in SEVEN])

LAST_ROW = 1001        # entry rows 2..1001 (row 2 is the example)
EXAMPLE_MARK = "EXAMPLE"

HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="E7E6E6")
AUTO_FONT = Font(bold=True, italic=True, color="808080")
EXAMPLE_FONT = Font(italic=True, color="808080")
LATER_FONT = Font(color="808080")
MISSING_FILL = PatternFill("solid", fgColor="F8CBAD")
DONE_FILL = PatternFill("solid", fgColor="C6EFCE")


def cell_key(area, kind):
    """The label a target cell goes by in Progress and in the helper columns."""
    return f"{area} | studio" if kind == "studio" else f"{area} | {kind} room"


def existing_cells():
    """Per target cell, from the seeded build (manual rows excluded): rows,
    distinct buildings, and the building names already counted."""
    df = pd.read_csv(LISTINGS)
    df = df[df["source"] != "manual"]
    out = {}
    for _, area, kind in TARGETS:
        if kind == "studio":
            g = df[(df["property_type"] == "condo") & (df["bedrooms"] == 0) & (df["area"] == area)]
        else:
            g = df[(df["property_type"] == "room") & (df["room_type"] == kind) & (df["area"] == area)]
        names = sorted({str(b).strip() for b in g["building"].dropna() if building_key(b)})
        out[cell_key(area, kind)] = {
            "rows": len(g),
            "buildings": len({building_key(b) for b in g["building"]} - {None}),
            "names": names,
        }
    return out


def snapshot_date():
    try:
        with open(COVERAGE, encoding="utf-8") as f:
            return json.load(f)["generated_at"][:10]
    except (OSError, KeyError, ValueError):
        return "unknown"


def header(ws, names, widths, auto=()):
    for col, (name, width) in enumerate(zip(names, widths), start=1):
        cell = ws.cell(row=1, column=col, value=name)
        cell.font = AUTO_FONT if name in auto else HEADER_FONT
        cell.fill = HEADER_FILL
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"


def validate(ws, rule, cells):
    ws.add_data_validation(rule)
    rule.add(cells)


def entry_validations(ws, cols, min_price):
    """Dropdowns and checks for an entry sheet. `cols` maps field -> column letter."""
    def span(col):
        return f"{col}2:{col}{LAST_ROW}"

    validate(ws, DataValidation(
        type="list", formula1="Areas", allow_blank=True, showErrorMessage=True,
        errorTitle="Not a known area",
        error='Pick an area from the list. A name used in both states needs its state, e.g. "Cheras (KL)".',
        showInputMessage=True, promptTitle="area", prompt="Pick from the list (type to jump)."),
        span(cols["area"]))
    if "room_type" in cols:
        validate(ws, DataValidation(
            type="list", formula1="RoomTypes", allow_blank=True, showErrorMessage=True,
            errorTitle="Room type", error="master or common (a single or middle room counts as common)."),
            span(cols["room_type"]))
    validate(ws, DataValidation(
        type="whole", operator="between", formula1=str(min_price), formula2=str(PRICE_MAX),
        allow_blank=True, showErrorMessage=True, errorTitle="Monthly rent",
        error=f"Whole ringgit per month, {min_price:,} to {PRICE_MAX:,}. Lower than RM{min_price} "
              "is not a real monthly rent for this type (a daily price?).",
        showInputMessage=True, promptTitle="price", prompt="Monthly rent in RM, whole number."),
        span(cols["price"]))
    validate(ws, DataValidation(
        type="textLength", operator="greaterThan", formula1="0", allow_blank=True,
        showInputMessage=True, promptTitle="building (required)",
        prompt="Development or building name; the street if there is none. "
               "Rows without it are not imported."),
        span(cols["building"]))
    validate(ws, DataValidation(
        type="list", formula1="SourceSites", allow_blank=True, showErrorMessage=True,
        errorTitle="Source site", error="Pick a site from the list, or other."),
        span(cols["source_site"]))
    validate(ws, DataValidation(
        type="date", operator="between", formula1="DATE(2026,1,1)", formula2="TODAY()",
        allow_blank=True, showErrorMessage=True, errorTitle="Date seen",
        error="A date from 2026 up to today.",
        showInputMessage=True, promptTitle="date_seen", prompt="Press Ctrl+; for today's date."),
        span(cols["date_seen"]))
    validate(ws, DataValidation(
        type="textLength", operator="lessThanOrEqual", formula1="2000", allow_blank=True,
        showInputMessage=True, promptTitle="url (optional)",
        prompt="Kept in this workbook only; never imported into the database."),
        span(cols["url"]))

    # Excel cannot make a cell required: a row with an area or a price but no
    # building turns the building cell red, and the importer rejects it.
    b, a, p = cols["building"], cols["area"], cols["price"]
    ws.conditional_formatting.add(
        f"{b}2:{b}{LAST_ROW}",
        FormulaRule(formula=[f'AND(OR(${a}2<>"",${p}2<>""),TRIM(${b}2)="")'], fill=MISSING_FILL))

    for r in range(2, LAST_ROW + 1):
        ws[f"{p}{r}"].number_format = "#,##0"
        ws[f"{cols['date_seen']}{r}"].number_format = "yyyy-mm-dd"


def valid_row(cols, r, min_price):
    """The Excel condition for a row the importer will accept (example row excluded)."""
    a, p, b = cols["area"], cols["price"], cols["building"]
    parts = [f'${a}{r}<>""', f"ISNUMBER(${p}{r})", f"${p}{r}>={min_price}", f"${p}{r}<={PRICE_MAX}",
             f'TRIM(${b}{r})<>""', f'LEFT(UPPER(TRIM(${b}{r})),{len(EXAMPLE_MARK)})<>"{EXAMPLE_MARK}"']
    if "room_type" in cols:
        parts.insert(1, f'${cols["room_type"]}{r}<>""')
    return "AND(" + ",".join(parts) + ")"


def helper_formulas(ws, cols, min_price, kind):
    """Two auto columns per row: the target cell the row counts toward, and
    1 when its building is new — not already in the database for that cell
    (Lists) and the first time it appears in this sheet."""
    key, new, b = cols["cell"], cols["new_building"], cols["building"]
    for r in range(2, LAST_ROW + 1):
        if kind == "room":
            t = cols["room_type"]
            room = (f'IF(OR(LOWER(TRIM(${t}{r}))="single",LOWER(TRIM(${t}{r}))="middle"),'
                    f'"common",LOWER(TRIM(${t}{r})))')
            label = f'${cols["area"]}{r}&" | "&{room}&" room"'
        else:
            label = f'${cols["area"]}{r}&" | studio"'
        ws[f"{key}{r}"] = f'=IF({valid_row(cols, r, min_price)},{label},"")'
        ws[f"{new}{r}"] = (
            f'=IF(${key}{r}="",0,IF(COUNTIFS(${key}$2:${key}{r},${key}{r},${b}$2:${b}{r},TRIM(${b}{r}))>1,0,'
            f'IF(COUNTIFS(KnownCell,${key}{r},KnownBuilding,TRIM(${b}{r}))>0,0,1)))')
        for col in (key, new):
            ws[f"{col}{r}"].font = LATER_FONT


def build(existing, today, snapshot):
    wb = Workbook()

    # ---- Rooms ------------------------------------------------------------
    rooms = wb.active
    rooms.title = "Rooms"
    room_cols = dict(area="A", room_type="B", price="C", building="D", source_site="E",
                     date_seen="F", url="G", cell="H", new_building="I")
    header(rooms, ["area", "room_type", "price", "building", "source_site", "date_seen", "url",
                   "cell (auto)", "new building (auto)"],
           [24, 12, 10, 36, 14, 12, 44, 30, 20], auto=("cell (auto)", "new building (auto)"))
    rooms.append(["Setapak", "common", 450, f"{EXAMPLE_MARK} – building name (not imported)",
                  "iProperty", today, None])
    for col in "ABCDEFG":
        rooms[f"{col}2"].font = EXAMPLE_FONT
    entry_validations(rooms, room_cols, ROOM_MIN_PRICE)
    helper_formulas(rooms, room_cols, ROOM_MIN_PRICE, "room")

    # ---- Studios ----------------------------------------------------------
    studios = wb.create_sheet("Studios")
    studio_cols = dict(area="A", price="B", building="C", source_site="D", date_seen="E", url="F",
                       cell="G", new_building="H")
    header(studios, ["area", "price", "building", "source_site", "date_seen", "url",
                     "cell (auto)", "new building (auto)"],
           [24, 10, 36, 14, 12, 44, 26, 20], auto=("cell (auto)", "new building (auto)"))
    studios.append(["Subang Jaya", 1500, f"{EXAMPLE_MARK} – building name (not imported)",
                    "PropertyGuru", today, None])
    for col in "ABCDEF":
        studios[f"{col}2"].font = EXAMPLE_FONT
    entry_validations(studios, studio_cols, STUDIO_MIN_PRICE)
    helper_formulas(studios, studio_cols, STUDIO_MIN_PRICE, "studio")

    # ---- Progress ---------------------------------------------------------
    progress = wb.create_sheet("Progress")
    header(progress, ["priority", "cell", "DB rows", "DB buildings", "rows needed", "rows entered",
                      "distinct buildings entered", "still needed", "status", "buildings already in DB"],
           [11, 30, 9, 13, 12, 13, 25, 13, 8, 60])
    first = 2
    for i, (priority, area, kind) in enumerate(TARGETS):
        r = first + i
        key = cell_key(area, kind)
        have = existing[key]
        needed = max(0, MIN_LISTINGS - have["rows"], MIN_BUILDINGS - have["buildings"])
        sheet, kcol, ncol = ("Studios", "G", "H") if kind == "studio" else ("Rooms", "H", "I")
        progress.append([
            priority, key, have["rows"], have["buildings"], needed,
            f"=COUNTIFS({sheet}!${kcol}$2:${kcol}${LAST_ROW},$B{r})",
            f"=SUMIFS({sheet}!${ncol}$2:${ncol}${LAST_ROW},{sheet}!${kcol}$2:${kcol}${LAST_ROW},$B{r})",
            f"=MAX(0,{MIN_LISTINGS}-($C{r}+$F{r}),{MIN_BUILDINGS}-($D{r}+$G{r}))",
            f'=IF(AND($C{r}+$F{r}>={MIN_LISTINGS},$D{r}+$G{r}>={MIN_BUILDINGS}),"✅","")',
            ", ".join(have["names"]) or "—",
        ])
        if priority.startswith("3"):
            for cell in progress[r]:
                cell.font = LATER_FONT
        progress[f"I{r}"].alignment = Alignment(horizontal="center")
    last = first + len(TARGETS) - 1
    total = last + 1
    progress.append(["", "Total", f"=SUM(C{first}:C{last})", "", f"=SUM(E{first}:E{last})",
                     f"=SUM(F{first}:F{last})", f"=SUM(G{first}:G{last})", f"=SUM(H{first}:H{last})",
                     f'=COUNTIF(I{first}:I{last},"✅")&" of {len(TARGETS)}"'])
    for cell in progress[total]:
        cell.font = HEADER_FONT
    progress.conditional_formatting.add(
        f"A{first}:J{last}", FormulaRule(formula=[f'$I{first}="✅"'], fill=DONE_FILL))
    notes = [
        f"✅ = at least {MIN_LISTINGS} rows from at least {MIN_BUILDINGS} buildings, counting the DB.",
        f"DB = the baseline built {snapshot} (Kaggle + Aug 2026 scrape), manual rows excluded.",
        "A building already in the DB for that cell, or repeated, adds a row but not a building.",
        "Only rows the importer will accept count (area, price in range, building; not the example).",
        "Building names match ignoring case only; the importer's table after the rebuild is final.",
    ]
    progress.column_dimensions["L"].width = 90
    for i, note in enumerate(notes, start=1):
        progress[f"L{i}"] = note
        progress[f"L{i}"].font = LATER_FONT

    # ---- Lists (hidden) ---------------------------------------------------
    lists = wb.create_sheet("Lists")
    areas = sorted(config.CANONICAL_AREAS, key=str.lower)
    known = [(key, name) for key, have in existing.items() for name in have["names"]]
    columns = {"A": ("area", areas), "B": ("room_type", ROOM_TYPES), "C": ("source_site", SOURCE_SITES),
               "E": ("cell", [k for k, _ in known] or [""]), "F": ("building already in DB", [n for _, n in known] or [""])}
    for col, (title, values) in columns.items():
        lists[f"{col}1"] = title
        lists[f"{col}1"].font = HEADER_FONT
        for i, value in enumerate(values, start=2):
            lists[f"{col}{i}"] = value
        lists.column_dimensions[col].width = 32
    lists.sheet_state = "hidden"
    for name, col, values in [("Areas", "A", areas), ("RoomTypes", "B", ROOM_TYPES),
                              ("SourceSites", "C", SOURCE_SITES),
                              ("KnownCell", "E", known or [""]), ("KnownBuilding", "F", known or [""])]:
        wb.defined_names[name] = DefinedName(name, attr_text=f"Lists!${col}$2:${col}${1 + len(values)}")

    wb.calculation.fullCalcOnLoad = True
    wb.active = 0
    return wb


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--force", action="store_true", help="overwrite an existing workbook")
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args(argv)
    if os.path.exists(args.out) and not args.force:
        sys.exit(f"{args.out} exists and may hold your entries; pass --force to overwrite it.")

    existing = existing_cells()
    wb = build(existing, date.today(), snapshot_date())
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    wb.save(args.out)
    print(f"wrote {args.out}")
    for priority, area, kind in TARGETS:
        key = cell_key(area, kind)
        have = existing[key]
        needed = max(0, MIN_LISTINGS - have["rows"], MIN_BUILDINGS - have["buildings"])
        print(f"  {priority:<9} {key:<32} DB {have['rows']} rows / {have['buildings']} bldg   needs {needed}")


if __name__ == "__main__":
    main()
