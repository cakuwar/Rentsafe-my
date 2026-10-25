"""Tests for the baseline pipeline (scripts/baseline) and the room-type parser fix.

Run with: nlp-service/.venv/Scripts/python -m unittest tests.test_baseline -v
"""
import os
import sys
import tempfile
import unittest
from dataclasses import replace

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.baseline import adjust  # noqa: E402
from scripts.baseline.areas import refine_scraped_area  # noqa: E402
from scripts.baseline.cleaning import DropLog, clean, dedupe_across  # noqa: E402
from scripts.baseline.schema import FIELDS, conform, stratum_status  # noqa: E402
from scripts.baseline.sources import REGISTRY  # noqa: E402
from scripts.scrapers import next_data  # noqa: E402
from scripts.scrapers.normalize import (  # noqa: E402
    normalize_area, normalize_room_type, normalize_row, normalize_tenants)


def listing(**overrides):
    row = {field: None for field in FIELDS}
    row.update(source="kaggle", building="Tower A", area="Kajang", property_type="condo",
               bedrooms=3, size_sqft=900, price_raw=1500)
    row.update(overrides)
    return row


def frame(*rows):
    return pd.DataFrame([listing(**r) for r in rows])


class AreaTests(unittest.TestCase):
    def test_sub_areas_stay_separate(self):
        self.assertEqual(normalize_area("Damansara Heights"), ("Damansara Heights", False))
        self.assertEqual(normalize_area("Damansara Perdana"), ("Damansara Perdana", False))
        self.assertEqual(normalize_area("Kampung Kerinchi (Bangsar South)"), ("Bangsar South", False))
        self.assertEqual(normalize_area("Pudu"), ("Pudu", False))

    def test_dual_state_names_need_the_state(self):
        self.assertEqual(normalize_area("Cheras", "Kuala Lumpur"), ("Cheras (KL)", False))
        self.assertEqual(normalize_area("Cheras", "Selangor"), ("Cheras (Selangor)", False))
        self.assertEqual(normalize_area("Cheras"), ("Cheras", True))
        self.assertEqual(normalize_area("Cheras (KL)"), ("Cheras (KL)", False))
        self.assertEqual(normalize_area("Bandar Mahkota Cheras"), ("Bandar Mahkota Cheras", False))

    def test_aliases_match_whole_words_only(self):
        self.assertEqual(normalize_area("PJ"), ("Petaling Jaya", False))
        self.assertEqual(normalize_area("Apjx"), ("Apjx", True))
        self.assertEqual(normalize_area("Subang"), ("Subang Jaya", False))
        self.assertEqual(normalize_area("Jalan Klang Lama (Old Klang Road)"), ("Old Klang Road", False))

    def test_generic_and_junk_need_review(self):
        for raw in ("Kuala Lumpur", "360", "Others"):
            self.assertTrue(normalize_area(raw, "Selangor")[1], raw)

    def test_scraped_title_refines_within_its_district(self):
        self.assertEqual(refine_scraped_area("Skyline KL, Pudu, KL City Centre", "", "KL City Centre",
                                             "Kuala Lumpur"), "Pudu")
        self.assertEqual(refine_scraped_area("Pavilion Damansara Heights", "", "Damansara",
                                             "Kuala Lumpur"), "Damansara Heights")
        self.assertEqual(refine_scraped_area("Mossaz @ Empire City, Damansara Perdana", "", "Damansara",
                                             "Selangor"), "Damansara Perdana")
        # A developer's name is not a place: Sunway Avila is in Wangsa Maju.
        self.assertEqual(refine_scraped_area("Sunway Avila Residences, Seksyen 1 Wangsa Maju, Wangsa Maju",
                                             "", "Wangsa Maju", "Kuala Lumpur"), "Wangsa Maju")
        # Serdang Jaya is a neighbourhood of Seri Kembangan, not Serdang.
        self.assertEqual(refine_scraped_area("Univ 360 Place, Serdang Jaya, Seri Kembangan", "",
                                             "Seri Kembangan", "Selangor"), "Seri Kembangan")


class RoomParserTests(unittest.TestCase):
    CARD = {
        "id": 501598036, "localizedTitle": "M Astra", "bedrooms": 0, "bathrooms": 1,
        "price": {"value": 1000}, "url": "/property/setapak/m-astra/rent-501598036/",
        "additionalData": {"districtText": "Setapak", "regionText": "Kuala Lumpur"},
        "property": {"subTypeText": "Service Residence"},
        "listingFeatures": [[{"dataAutomationId": "listing-card-v2-room-type", "text": "Master Room"},
                             {"dataAutomationId": "listing-card-v2-tenants", "text": "2 pax (female)"}]],
    }

    def test_room_card_becomes_a_room_not_a_0br_condo(self):
        row = normalize_row(next_data.row_from_listing_data(self.CARD, "https://www.iproperty.com.my"))
        self.assertEqual(row["property_type"], "room")
        self.assertEqual(row["room_type"], "master")
        self.assertIsNone(row["bedrooms"])
        self.assertEqual((row["max_tenants"], row["tenant_gender"]), (2, "female"))
        self.assertEqual(row["portal_listing_id"], "501598036")

    def test_flats_are_their_own_type(self):
        from scripts.scrapers.normalize import normalize_property_type
        self.assertEqual(normalize_property_type("Flat"), "flat")
        self.assertEqual(normalize_property_type("Rumah Pangsa PPR Seri Kota"), "flat")
        self.assertEqual(normalize_property_type("Pangsapuri Seri Jati"), "apartment")
        self.assertEqual(normalize_property_type("Service Residence"), "condo")

    def test_room_types(self):
        self.assertEqual(normalize_room_type("Common Room"), "common")
        self.assertEqual(normalize_room_type("single"), "common")
        self.assertEqual(normalize_room_type("Middle Room"), "common")
        self.assertEqual(normalize_room_type("Master Room"), "master")
        self.assertIsNone(normalize_room_type("Room for rent"))
        self.assertEqual(normalize_tenants("1 pax"), (1, None))


class CleaningTests(unittest.TestCase):
    def run_clean(self, *rows):
        log = DropLog()
        return clean(frame(*rows), "kaggle", log), log.drops["kaggle"], log.notes["kaggle"]

    def test_price_rules(self):
        out, drops, _ = self.run_clean(
            {"price_raw": 99}, {"price_raw": 100_001},
            {"price_raw": 45_000, "size_sqft": 603},                 # sale price
            {"price_raw": 14_000, "size_sqft": 1216, "area": "KLCC"},  # luxury rent, 11.5 psf: kept
            {"price_raw": 250},                                      # whole unit: per-day
            {"price_raw": 300, "size_sqft": 1500},                   # 0.2 psf: per-day
            {"price_raw": 250, "property_type": "room", "room_type": "common", "bedrooms": None},
        )
        self.assertEqual(drops["price_outside_RM100_100000"], 2)
        self.assertEqual(drops["looks_like_sale_price"], 1)
        self.assertEqual(drops["looks_like_per_day_or_week"], 2)
        self.assertEqual(sorted(out["price_raw"]), [250, 14_000])

    def test_structure_rules(self):
        out, drops, notes = self.run_clean(
            {"source_listing_id": "1"}, {"source_listing_id": "1"},
            {"size_sqft": 1, "price_raw": 1400},                     # size emptied, row kept
            {"bedrooms": None},
            {"bedrooms": 7},
            {"bedrooms": 0, "size_sqft": None},                      # unconfirmed 0BR: dropped
            {"bedrooms": 0, "size_sqft": None, "_studio_confirmed": True},
            {"property_type": "room", "room_type": None, "bedrooms": None, "price_raw": 600},
        )
        self.assertEqual(drops["duplicate_listing_id"], 1)
        self.assertEqual(drops["missing_bedrooms"], 1)
        self.assertEqual(drops["zero_bedroom_no_size_unconfirmed"], 1)
        self.assertEqual(drops["room_type_unknown"], 1)
        self.assertEqual(notes["size_implausible_set_empty"], 1)
        self.assertEqual(notes["bedrooms_5plus_bucketed_to_4"], 1)
        self.assertEqual(len(out), 4)
        self.assertEqual(out["bedrooms"].max(), 4)

    def test_unit_key_dedupe_keeps_one_per_group(self):
        rows = [{"source_listing_id": str(i), "building": "Laguna Biru", "price_raw": 800, "size_sqft": 850,
                 "bedrooms": 3, "area": "Rawang"} for i in range(4)]
        rows.append({"source_listing_id": "9", "building": "Laguna Biru", "price_raw": 850, "size_sqft": 850,
                     "bedrooms": 3, "area": "Rawang"})
        rows.append({"source_listing_id": "10", "building": None, "price_raw": 800, "size_sqft": 850,
                     "bedrooms": 3, "area": "Rawang"})
        rows.append({"source_listing_id": "11", "building": None, "price_raw": 800, "size_sqft": 850,
                     "bedrooms": 3, "area": "Rawang"})
        log = DropLog()
        out = clean(frame(*rows), "kaggle", log, dedupe_unit_key=True)
        self.assertEqual(log.drops["kaggle"]["duplicate_unit_key"], 3)
        self.assertEqual(len(out), 4)  # one Laguna Biru at 800, one at 850, both unknown buildings
        self.assertEqual(len(clean(frame(*rows), "kaggle", DropLog())), 7)  # off by default

    def test_cross_source_dedupe_is_one_to_one(self):
        scraped = frame({"source": "scraped", "building": "Laguna Biru", "price_raw": 800, "size_sqft": 850})
        kaggle = frame(*[{"building": "Laguna Biru", "price_raw": 800, "size_sqft": 850}] * 8)
        log = DropLog()
        out = dict(dedupe_across([("scraped", scraped), ("kaggle", kaggle)], log))
        self.assertEqual(len(out["kaggle"]), 7)
        self.assertEqual(log.drops["kaggle"]["duplicate_across_sources"], 1)


class StatusAndAdjustTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(stratum_status(5, 3), "scorable")
        self.assertEqual(stratum_status(8, 1), "few-bldg")
        self.assertEqual(stratum_status(4, 4), "thin")
        self.assertEqual(stratum_status(2, 2), "sparse")
        self.assertEqual(stratum_status(0, 0), "empty")

    @staticmethod
    def stratum(source, area, price, n=5):
        return [{"source": source, "area": area, "building": f"{area} {i}", "price_raw": price}
                for i in range(n)]

    def test_factor_is_the_median_ratio_over_shared_scorable_strata(self):
        ext, ref = [], []
        for area, (k, s) in {"A": (1000, 1100), "B": (2000, 2400), "C": (1000, 1300)}.items():
            ext += self.stratum("kaggle", area, k)
            ref += self.stratum("scraped", area, s)
        result = adjust.compute(frame(*ext), frame(*ref))
        self.assertEqual(result["strata_used"], 3)
        self.assertEqual(result["stratum_median_factor"], 1.2)
        self.assertEqual(result["spread"], {"min_ratio": 1.1, "max_ratio": 1.3})
        self.assertTrue(result["applied"])

    def test_fewer_than_three_strata_gives_no_stratum_factor(self):
        ext = self.stratum("kaggle", "A", 1000) + self.stratum("kaggle", "B", 1000)
        ref = self.stratum("scraped", "A", 1200) + self.stratum("scraped", "B", 1200, n=4)
        result = adjust.compute(frame(*ext), frame(*ref))
        self.assertEqual(result["strata_used"], 1)
        self.assertIsNone(result["stratum_median_factor"])

    def test_building_matched_factor_needs_three_pairs(self):
        ext = self.stratum("kaggle", "A", 1000) + self.stratum("kaggle", "B", 2000)
        ref = self.stratum("scraped", "A", 1200) + self.stratum("scraped", "B", 2400)
        result = adjust.compute(frame(*ext), frame(*ref))
        self.assertEqual(result["building_matched"]["all_pairs"]["pairs"], 10)
        self.assertEqual(result["factor"], 1.2)
        self.assertEqual(result["applied_method"], "building_matched")
        # No building listed in both sources: nothing to compare, nothing applied.
        other = [dict(r, building=f"other {i}") for i, r in enumerate(ref)]
        result = adjust.compute(frame(*ext), frame(*other))
        self.assertIsNone(result["factor"])
        self.assertEqual(result["status"], "insufficient_overlap")
        self.assertEqual(len(result["fallbacks"]), 3)

    def test_apply_scales_only_adjusted_sources(self):
        df = conform(frame({"price_raw": 1000}, {"source": "scraped", "price_raw": 1000}))
        out = adjust.apply(df, 1.2, ["kaggle"])
        self.assertEqual(list(out["price_adjusted"]), [1200.0, 1000.0])
        self.assertEqual(list(adjust.apply(df, None, ["kaggle"])["price_adjusted"]), [1000.0, 1000.0])


class LoaderTests(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_kaggle_mapping(self):
        path = self.write(
            "ads_id,prop_name,completion_year,monthly_rent,location,property_type,rooms,parking,"
            "bathroom,size,furnished,facilities,additional_facilities,region\n"
            "1,Pacific Star,,RM 1 200 per month,Selangor - Petaling Jaya,Studio,1,,1,450 sq.ft.,,,,Selangor\n"
            "2,Laguna Biru,,RM 800 per month,Selangor - Rawang,Flat,3,,1,850 sq.ft.,,,,Selangor\n"
            "3,Aster Residence Cheras,,RM 3 000 per month,Selangor - 360,Condominium,3,,2,1000 sq.ft.,,,,Selangor\n"
            "4,\"Room for rent , KJ Room Stay\",,RM 600 per month,Selangor - Gombak,Others,1,,1,390 sq.ft.,,,,Selangor\n"
            "5,Segar Courts,,RM 2 300 per month,Kuala Lumpur - Cheras,Condominium,More than 10,,2,1170 sq.ft.,,,,Kuala Lumpur\n"
        )
        log = DropLog()
        df, info = REGISTRY["kaggle"].loader(replace(REGISTRY["kaggle"], path=path), log)
        by_id = df.set_index("source_listing_id")
        self.assertEqual((by_id.loc["1", "property_type"], by_id.loc["1", "bedrooms"]), ("condo", 0))
        self.assertTrue(by_id.loc["1", "_studio_confirmed"])
        self.assertEqual((by_id.loc["2", "property_type"], by_id.loc["2", "source_subtype"]), ("flat", "Flat"))
        self.assertEqual(by_id.loc["4", "property_type"], "room")
        self.assertEqual(by_id.loc["5", "area"], "Cheras (KL)")
        self.assertEqual(info["unmapped_areas"], {"Selangor - 360": 1})
        self.assertNotIn("facilities", df.columns)

    def test_manual_workbook(self):
        from datetime import date

        from openpyxl import Workbook
        wb = Workbook()
        rooms = wb.active
        rooms.title = "Rooms"
        rooms.append(["area", "room_type", "price", "building", "source_site", "date_seen", "url"])
        for row in [
            ["Setapak", "common", 450, "EXAMPLE – building name (not imported)", "iProperty", date(2026, 10, 19), None],
            ["Setapak", "single", 650, "Jalan Genting Kelang", "iBilik", date(2026, 10, 15), "https://x"],  # row 3
            ["Cheras", "master", 900, "Taman Connaught", "Mudah", date(2026, 10, 15), None],                # row 4
            ["Cheras (KL)", "master", 900, "Taman Connaught", "Mudah", date(2026, 10, 15), None],           # row 5
            [None, None, None, None, None, None, None],                                                    # blank
            ["Shah Alam", "common", 120, "Seksyen 7", "Facebook", date(2026, 10, 15), None],                # row 7
            ["Shah Alam", "common", 500, "", "Facebook", date(2026, 10, 15), None],                         # row 8
            ["Shah Alam", "bedspace", 300, "i-City", "other", date(2026, 10, 15), None],                    # row 9
        ]:
            rooms.append(row)
        studios = wb.create_sheet("Studios")
        studios.append(["area", "price", "building", "source_site", "date_seen", "url"])
        studios.append(["Subang Jaya", 1600, "Sunway Geo Avenue", "PropertyGuru", date(2026, 10, 18), None])
        studios.append(["Subang Jaya", 250, "Cheap Block", "PropertyGuru", date(2026, 10, 18), None])
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        wb.save(handle.name)

        log = DropLog()
        df, info = REGISTRY["manual"].loader(replace(REGISTRY["manual"], path=handle.name), log)
        rejected = {(r["sheet"], r["row"]): r["reason"] for r in info["rejected"]}
        self.assertEqual(set(rejected), {("Rooms", 4), ("Rooms", 7), ("Rooms", 8), ("Rooms", 9), ("Studios", 3)})
        self.assertIn("needs its state", rejected[("Rooms", 4)])          # plain "Cheras" is not guessed
        self.assertIn("outside RM150", rejected[("Rooms", 7)])
        self.assertEqual(rejected[("Rooms", 8)], "missing building")
        self.assertIn("not master or common", rejected[("Rooms", 9)])
        self.assertIn("outside RM300", rejected[("Studios", 3)])
        self.assertEqual((info["skipped_example"], info["accepted"]), (1, {"Rooms": 2, "Studios": 1}))
        self.assertEqual(info["mapped_to_common"], [{"sheet": "Rooms", "row": 3, "room_type": "single"}])

        self.assertEqual(list(df["room_type"]), ["common", "master", None])
        studio = df.iloc[2]
        self.assertEqual((studio["property_type"], studio["bedrooms"], studio["_studio_confirmed"]), ("condo", 0, True))
        self.assertEqual(list(df["collected_at"]), ["2026-10-15", "2026-10-15", "2026-10-18"])
        for column in ("url", "source_site"):
            self.assertNotIn(column, df.columns)
        self.assertTrue(df["size_sqft"].isna().all() and df["private_bathroom"].isna().all())
        kept = clean(df, "manual", log)                                    # a size-less studio survives cleaning
        self.assertEqual(len(kept), 3)


class ManualWorkbookTests(unittest.TestCase):
    """The hand-entry workbook (scripts/baseline/manual_workbook.py)."""

    def setUp(self):
        from datetime import date

        from openpyxl import load_workbook

        from scripts.baseline import manual_workbook as mw
        self.mw = mw
        existing = {mw.cell_key(area, kind): {"rows": 0, "buildings": 0, "names": []}
                    for _, area, kind in mw.TARGETS}
        existing[mw.cell_key("Setapak", "common")] = {"rows": 5, "buildings": 1, "names": ["M Astra"]}
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        mw.build(existing, date(2026, 10, 19), "2026-10-15").save(handle.name)
        self.path = handle.name
        self.wb = load_workbook(handle.name)

    def test_sheets_headers_and_example_row(self):
        self.assertEqual(self.wb.sheetnames, ["Rooms", "Studios", "Progress", "Lists"])
        self.assertEqual(self.wb["Lists"].sheet_state, "hidden")
        self.assertEqual([c.value for c in self.wb["Rooms"][1]][:7],
                         ["area", "room_type", "price", "building", "source_site", "date_seen", "url"])
        self.assertEqual([c.value for c in self.wb["Studios"][1]][:6],
                         ["area", "price", "building", "source_site", "date_seen", "url"])
        for name in ("Rooms", "Studios", "Progress"):
            self.assertEqual(self.wb[name].freeze_panes, "A2")
        self.assertTrue(self.wb["Rooms"]["D2"].value.startswith("EXAMPLE"))
        self.assertTrue(self.wb["Rooms"]["A2"].font.italic)

    def test_dropdowns_and_checks(self):
        def rules(ws):
            return {(dv.type, dv.formula1, dv.formula2) for dv in ws.data_validations.dataValidation}
        rooms, studios = rules(self.wb["Rooms"]), rules(self.wb["Studios"])
        for name in ("Areas", "RoomTypes", "SourceSites"):
            self.assertIn(("list", name, None), rooms)
        self.assertIn(("whole", "150", "100000"), rooms)    # the room floor, not 50
        self.assertIn(("whole", "300", "100000"), studios)  # the whole-unit floor
        self.assertIn(("date", "DATE(2026,1,1)", "TODAY()"), studios)
        areas = [c.value for c in self.wb["Lists"]["A"][1:] if c.value]
        self.assertEqual(len(areas), 125)
        self.assertIn("Cheras (KL)", areas)
        self.assertNotIn("Cheras", areas)
        self.assertEqual(set(self.wb.defined_names),
                         {"Areas", "RoomTypes", "SourceSites", "KnownCell", "KnownBuilding"})

    def test_progress_lists_the_priorities_in_order(self):
        ws = self.wb["Progress"]
        cells = [ws[f"B{r}"].value for r in range(2, 20)]
        self.assertEqual(cells[:7], [f"{a} | common room" for a in self.mw.SEVEN])
        self.assertEqual(cells[7:11], [f"{a} | studio" for a in
                                       ["Setapak", "Cheras (KL)", "Puchong (Selangor)", "Subang Jaya"]])
        self.assertEqual(cells[11:], [f"{a} | master room" for a in self.mw.SEVEN])
        self.assertEqual([ws["C2"].value, ws["D2"].value, ws["E2"].value], [5, 1, 2])  # needs 2 more buildings
        self.assertTrue(ws["F2"].value.startswith("=COUNTIFS(Rooms!"))
        self.assertTrue(ws["F9"].value.startswith("=COUNTIFS(Studios!"))
        self.assertEqual(ws["B20"].value, "Total")

    def test_refuses_to_overwrite_entries(self):
        with self.assertRaises(SystemExit):
            self.mw.main(["--out", self.path])


if __name__ == "__main__":
    unittest.main()
