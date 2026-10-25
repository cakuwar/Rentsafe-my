"""Room and studio listings recorded by hand: data/raw/manual/manual_price_entry.xlsx
(made by scripts/baseline/manual_workbook.py and filled in while browsing).

Read straight from the workbook, no CSV step:
    Rooms    area, room_type, price, building, source_site, date_seen, url
             -> the room baseline (master | common; single / middle -> common)
    Studios  area, price, building, source_site, date_seen, url
             -> condo with 0 bedrooms, marked a confirmed studio so cleaning
                keeps it without a size

Size and private bathroom are not read: neither is a stratum key, and the
form never asks for them. source_site and url stay in the workbook; no
personal data is read.

A row that cannot be used is REJECTED, never repaired, and listed in the
loader's info by sheet and row number: an area that is not an exact
canonical name (so "Cheras" is rejected, not guessed), a missing building, a
price that is not a whole number in range, an unknown room type, or a date
that is not a date from 2026 up to today. Blank rows and the example row are
skipped.
"""
import os
from datetime import date, datetime

import pandas as pd
from openpyxl import load_workbook

from scripts.scrapers import config

from ..areas import resolve
from ..cleaning import PRICE_MAX
from ..manual_workbook import EXAMPLE_MARK, ROOM_MIN_PRICE, STUDIO_MIN_PRICE
from ..schema import empty_frame

SHEETS = {
    "Rooms": ["area", "room_type", "price", "building", "source_site", "date_seen", "url"],
    "Studios": ["area", "price", "building", "source_site", "date_seen", "url"],
}
ROOM_TYPES = {"master": "master", "common": "common", "single": "common", "middle": "common"}
EARLIEST = date(2026, 1, 1)

_CANONICAL = {name.lower(): name for name in config.CANONICAL_AREAS}


def _text(value):
    return "" if value is None else " ".join(str(value).split())


def _area(raw):
    area = _CANONICAL.get(raw.lower())
    if area:
        return area, None
    options = config.DUAL_STATE_AREAS.get(raw.lower())
    if options:
        return None, f'area "{raw}" needs its state: {" or ".join(options.values())}'
    hint = resolve(raw)
    return None, f'unknown area "{raw}"' + (f' (the list has "{hint}")' if hint else "")


def _price(value, low):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"price {_text(value)!r} is not a number"
    if value != int(value):
        return None, f"price {value} is not a whole number"
    if not low <= value <= PRICE_MAX:
        return None, f"price RM{int(value):,} is outside RM{low:,}-{PRICE_MAX:,}"
    return int(value), None


def _date(value, today):
    if value is None or _text(value) == "":
        return None, None
    if isinstance(value, datetime):
        value = value.date()
    elif not isinstance(value, date):
        try:
            value = date.fromisoformat(_text(value))
        except ValueError:
            return None, f"date_seen {_text(value)!r} is not a date"
    if not EARLIEST <= value <= today:
        return None, f"date_seen {value.isoformat()} is outside {EARLIEST.isoformat()} to today"
    return value.isoformat(), None


def read_workbook(path, today=None):
    """-> (rows, report). `rows` are accepted listings in the common schema;
    `report` has the counts, every rejection and every single/middle mapping."""
    today = today or date.today()
    wb = load_workbook(path, read_only=True, data_only=True)
    rows = []
    report = {"rows_read": {}, "accepted": {}, "rejected": [], "skipped_example": 0, "skipped_blank": 0,
              "mapped_to_common": [], "no_date": []}
    try:
        for sheet, columns in SHEETS.items():
            if sheet not in wb.sheetnames:
                raise ValueError(f"{path} has no {sheet} sheet")
            ws = wb[sheet]
            header = [_text(c) for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
            missing = [c for c in columns if c not in header]
            if missing:
                raise ValueError(f"{path} sheet {sheet} is missing columns: {missing}")
            at = {c: header.index(c) for c in columns}
            read = accepted = 0
            for number, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                get = {c: (values[i] if i < len(values) else None) for c, i in at.items()}
                if all(_text(get[c]) == "" for c in columns):
                    report["skipped_blank"] += 1
                    continue
                building = _text(get["building"])
                if building.upper().startswith(EXAMPLE_MARK):
                    report["skipped_example"] += 1
                    continue
                read += 1

                problems = []
                area, why = _area(_text(get["area"]))
                problems += [why] if why else []
                price, why = _price(get["price"], ROOM_MIN_PRICE if sheet == "Rooms" else STUDIO_MIN_PRICE)
                problems += [why] if why else []
                if not building:
                    problems.append("missing building")
                room_type = None
                if sheet == "Rooms":
                    typed = _text(get["room_type"]).lower()
                    room_type = ROOM_TYPES.get(typed)
                    if not room_type:
                        problems.append(f"room_type {typed!r} is not master or common"
                                        if typed else "missing room_type")
                seen, why = _date(get["date_seen"], today)
                problems += [why] if why else []

                if problems:
                    report["rejected"].append({"sheet": sheet, "row": number, "reason": "; ".join(problems)})
                    continue
                if sheet == "Rooms" and typed != room_type:
                    report["mapped_to_common"].append({"sheet": sheet, "row": number, "room_type": typed})
                if seen is None:
                    report["no_date"].append({"sheet": sheet, "row": number})
                accepted += 1
                rows.append({
                    "source": "manual", "source_listing_id": None, "building": building, "area": area,
                    "property_type": "room" if sheet == "Rooms" else "condo",
                    "source_subtype": f"manual {room_type} room" if sheet == "Rooms" else "manual studio",
                    "bedrooms": None if sheet == "Rooms" else 0, "room_type": room_type,
                    "private_bathroom": None, "size_sqft": None, "price_raw": price, "price_adjusted": None,
                    "collected_at": seen, "_studio_confirmed": sheet == "Studios",
                })
            report["rows_read"][sheet] = read
            report["accepted"][sheet] = accepted
    finally:
        wb.close()
    return rows, report


def load(source, log):
    path = os.path.join(config.ROOT, source.path)
    log.rows_in[source.name] = 0
    if not os.path.exists(path):
        return empty_frame(), {"file": source.path, "exists": False}

    rows, report = read_workbook(path)
    log.rows_in[source.name] = sum(report["rows_read"].values())
    for rejection in report["rejected"]:
        log.drops[source.name][f"rejected ({rejection['sheet']})"] += 1
    df = pd.DataFrame(rows) if rows else empty_frame().assign(_studio_confirmed=pd.Series(dtype=bool))
    return df, {"file": source.path, "exists": True, **report}
