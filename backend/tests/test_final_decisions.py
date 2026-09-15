"""Final Decisions tests against an isolated SQLite store; never touch the configured DB.

The endpoint SQL runs for real with attached ``incentive`` / ``mafsho`` schemas,
so the plan join (``final_incentive_plans`` → ``incentive_city_plan_mapping`` →
``incentive_type``) and the type-name resolution are exercised end to end.
Run: python -m unittest discover -s tests -v
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import final_decisions as final
from app.main import app

BASE = "/api/final-decisions"
DATE = "2026-09-16"

# incentive.incentive_active_city: the active city list the scores are named after
CITIES = [
    # id, city_id, city, box_city_name, city_group
    # Inserted out of order on purpose: the endpoint groups the cities itself.
    (1, 10, "tehran", "Tehran", "Top 4"),
    (2, 20, "kerman", "Kerman", "Tier 2"),
    (3, 30, "qom", "Qom", "Tier 3"),
    (4, 40, "mashhad", "Mashhad", "Zone X"),
    (5, 50, "karaj", "Karaj", "tehran-group"),
    (6, 60, "tabriz", "Tabriz", "TOP_4"),
    (7, 70, "isfahan", "Isfahan", "Tier-1"),
    (8, 80, "ahvaz", "Ahvaz", "Tier 4"),
    (9, 90, "rasht", "Rasht", None),
]

# incentive.incentive_scores: one row per city / business entity / score type
SCORES = [
    # id, incentive_date, city_id, business_entity_id, score_type, score
    (1, DATE, 10, "foodZooket", "performance", 0.42),
    (2, DATE, 10, "foodZooket", "weather", 0.18),
    (3, DATE, 20, "food", "performance", 0.61),
    (4, DATE, 20, "food", "order_level_increase", 0.30),
    # one score per extra city so each of them is listed
    (5, DATE, 30, "food", "performance", 0.11),
    (6, DATE, 40, "food", "performance", 0.22),
    (7, DATE, 50, "food", "performance", 0.33),
    (8, DATE, 60, "food", "performance", 0.44),
    (9, DATE, 70, "food", "performance", 0.55),
    (10, DATE, 80, "food", "performance", 0.66),
    (11, DATE, 90, "food", "performance", 0.77),
]

# mafsho.incentive_type: the same lookup the Cities tab shows
TYPES = [(1, "DAILY"), (2, "default"), (3, "ON-TOP-FOOD"), (4, "WEEKLY")]

# incentive.incentive_city_plan_mapping: id, city_id, incentive_type_id, business_entity
MAPPINGS = [
    (8, 20, 2, "food", None),
    (23, 10, 1, "foodZooket", None),
    (118, 10, 3, "foodZooket", "2026-09-14T09:00:00"),
    (132, 20, 1, "food", None),
    (122, 20, 4, "foodZooket", None),
    (133, 20, 1, "foodZooket", None),  # a second DAILY plan, for another entity
    (170, 99, 1, "food", None),  # city 99 has no scores, so no city row either
]

# incentive.final_incentive_plans: exactly the columns the tab reads
PLANS = [
    # id, incentive_date, plan_mapping_id, target_change, pr_change, control_bucket
    (1, DATE, 122, 1.000, 1.100, None),
    (2, DATE, 23, 1.000, 1.200, None),
    (3, DATE, 118, 1.000, 1.350, None),
    (4, DATE, 132, 1.000, 1.200, None),
    (5, DATE, 8, 1.000, 1.300, "[0.2, 0.2, 0.1]"),
    (8, DATE, 133, 1.050, 1.400, None),         # the second DAILY plan of kerman
    (6, "2026-09-17", 23, 1.000, 9.999, None),  # another date, must not leak in
    (7, DATE, 170, 1.000, 1.400, None),         # a city without scores: never listed
]


class FinalDecisionsAPITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        with self.engine.begin() as conn:
            conn.execute(text("ATTACH DATABASE ':memory:' AS incentive"))
            conn.execute(text("ATTACH DATABASE ':memory:' AS mafsho"))
            conn.execute(text("CREATE TABLE mafsho.incentive_type (id INTEGER PRIMARY KEY, name TEXT)"))
            conn.execute(text(
                "CREATE TABLE incentive.incentive_active_city (id INTEGER PRIMARY KEY, city_id INTEGER, "
                "city TEXT, box_city_name TEXT, city_group TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE incentive.incentive_scores (id INTEGER PRIMARY KEY, incentive_date TEXT, "
                "city_id INTEGER, business_entity_id TEXT, score_type TEXT, score REAL)"
            ))
            conn.execute(text(
                "CREATE TABLE incentive.business_entities (id TEXT PRIMARY KEY, name TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE incentive.incentive_city_plan_mapping (id INTEGER PRIMARY KEY, city_id INTEGER, "
                "incentive_type_id INTEGER, business_entity TEXT, created_at TEXT, deactivated_at TEXT)"
            ))
            conn.execute(text(
                "CREATE TABLE incentive.final_incentive_plans (id INTEGER PRIMARY KEY, updated_at TEXT, "
                "updated_by TEXT, incentive_date TEXT, plan_mapping_id INTEGER, target_change REAL, "
                "pr_change REAL, control_bucket TEXT)"
            ))
            conn.execute(text("INSERT INTO mafsho.incentive_type VALUES (:id, :name)"),
                         [{"id": i, "name": n} for i, n in TYPES])
            conn.execute(text("INSERT INTO incentive.incentive_active_city VALUES (:id, :city_id, :city, :box, :grp)"),
                         [{"id": i, "city_id": c, "city": city, "box": box, "grp": grp}
                          for i, c, city, box, grp in CITIES])
            conn.execute(text("INSERT INTO incentive.incentive_scores VALUES (:id, :d, :city, :be, :st, :score)"),
                         [{"id": i, "d": d, "city": city, "be": be, "st": st, "score": sc}
                          for i, d, city, be, st, sc in SCORES])
            conn.execute(text("INSERT INTO incentive.incentive_city_plan_mapping VALUES (:id, :city, :type, :be, '2026-09-01T00:00:00', :off)"),
                         [{"id": i, "city": city, "type": t, "be": be, "off": off}
                          for i, city, t, be, off in MAPPINGS])
            conn.execute(text(
                "INSERT INTO incentive.final_incentive_plans (id, updated_at, updated_by, incentive_date, "
                "plan_mapping_id, target_change, pr_change, control_bucket) "
                "VALUES (:id, '2026-09-15 13:17:22', 'System', :d, :mapping, :target, :pr, :bucket)"
            ), [{"id": i, "d": d, "mapping": m, "target": t, "pr": p, "bucket": b}
                for i, d, m, t, p, b in PLANS])

        for name, value in {
            "engine": self.engine,
            "SCORES_TABLE_SQL": "`incentive`.`incentive_scores`",
            "ACTIVE_CITY_SQL": "`incentive`.`incentive_active_city`",
            "BUSINESS_ENTITIES_SQL": "`incentive`.`business_entities`",
            "PLANS_SQL": "`incentive`.`final_incentive_plans`",
            "PLAN_MAPPINGS_SQL": "`incentive`.`incentive_city_plan_mapping`",
            "INCENTIVE_TYPES_SQL": "`mafsho`.`incentive_type`",
            "FINAL_DECISION_PLAN_TYPE_ORDER": "DAILY,ON-TOP-FOOD",
            "FINAL_DECISION_GROUP_ORDER": "Tehran Group,Top 4,Tier 1,Tier 2,Tier 3",
        }.items():
            patcher = patch.object(final, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.engine.dispose)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def read(self, **params):
        res = self.client.get(BASE, params=params)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def city(self, data, city_id):
        return next(c for c in data["cities"] if str(c["city_id_raw"]) == str(city_id))

    def test_plans_are_grouped_by_city_and_ordered_by_type(self):
        data = self.read(incentive_date=DATE)

        self.assertEqual(data["plan_type_order"], ["DAILY", "ON-TOP-FOOD"])
        # 8 sample rows, but only the 6 of DAY belong to this date
        self.assertEqual(data["total_plans"], 6)
        self.assertIsNone(data["plans_error"])

        kerman = self.city(data, 20)
        self.assertEqual(kerman["plan_count"], 4)
        # DAILY (1st, two plans) → the unlisted "default" and WEEKLY last
        self.assertEqual(
            [p["incentive_type"] for p in kerman["plans"]], ["DAILY", "DAILY", "default", "WEEKLY"]
        )
        # inside one type the entity priority decides: foodZooket before food
        self.assertEqual(
            [p["business_entity"] for p in kerman["plans"]], ["foodZooket", "food", "food", "foodZooket"]
        )
        # the top plan is the DAILY one of the first entity, not the "default" row
        self.assertEqual(kerman["top_plan"]["id"], 8)
        self.assertEqual(kerman["top_plan"]["incentive_type"], "DAILY")
        self.assertEqual(kerman["top_plan"]["business_entity"], "foodZooket")

        tehran = self.city(data, 10)
        self.assertEqual(tehran["plan_count"], 2)
        self.assertEqual(
            [p["incentive_type"] for p in tehran["plans"]], ["DAILY", "ON-TOP-FOOD"]
        )

    def test_plan_fields_target_pr_bucket_and_updated_at(self):
        data = self.read(incentive_date=DATE)
        plan = next(p for p in self.city(data, 20)["plans"] if p["id"] == 5)

        self.assertEqual(plan["plan_mapping_id"], 8)
        self.assertEqual(plan["incentive_type_id"], 2)
        self.assertEqual(plan["incentive_type"], "default")
        self.assertEqual(plan["incentive_type_label"], "default")
        self.assertEqual(plan["business_entity"], "food")
        self.assertEqual(plan["target_change"], 1.0)
        self.assertEqual(plan["pr_change"], 1.3)
        self.assertEqual(plan["control_bucket"], [0.2, 0.2, 0.1])
        self.assertEqual(plan["updated_by"], "System")
        # MySQL returns a datetime (ISO, "T"), SQLite a text column as stored
        self.assertIn("2026-09-15", plan["updated_at"])
        self.assertIn("13:17:22", plan["updated_at"])
        self.assertTrue(plan["mapping_active"])

    def test_plans_of_a_city_without_scores_are_counted_but_not_listed(self):
        data = self.read(incentive_date=DATE)

        self.assertEqual(data["total_plans"], 6)
        self.assertEqual(data["plans_without_scores"], 1)
        self.assertEqual(data["plans_without_scores_cities"], ["City #99"])
        for city in data["cities"]:
            self.assertNotIn(99, [plan["city_id"] for plan in city["plans"]])

    def test_a_plan_without_a_bucket_keeps_it_null(self):
        data = self.read(incentive_date=DATE)
        plan = next(p for p in self.city(data, 20)["plans"] if p["id"] == 4)
        self.assertIsNone(plan["control_bucket"])

    def test_deactivated_mapping_is_reported_but_not_hidden(self):
        data = self.read(incentive_date=DATE)
        plan = next(p for p in self.city(data, 10)["plans"] if p["id"] == 3)
        self.assertFalse(plan["mapping_active"])
        self.assertTrue(plan["mapping_deactivated_at"])

    def test_scores_still_load_when_the_plans_table_is_missing(self):
        with patch.object(final, "PLANS_SQL", "`incentive`.`does_not_exist`"):
            data = self.read(incentive_date=DATE)

        self.assertIn("does_not_exist", data["plans_error"])
        self.assertEqual(data["total_plans"], 0)
        self.assertEqual(self.city(data, 20)["plan_count"], 0)
        self.assertIsNotNone(self.city(data, 20)["primary_entity"]["scores"]["performance"])

    def test_plan_type_rank_follows_the_configured_order(self):
        self.assertEqual(final._plan_type_rank("DAILY"), 0)
        self.assertEqual(final._plan_type_rank("daily"), 0)
        self.assertEqual(final._plan_type_rank("ON-TOP-FOOD"), 1)
        # "default" is not a plan type of this database: it is just another
        # unlisted type and comes after the configured ones.
        self.assertGreater(final._plan_type_rank("default"), 1)
        self.assertGreater(final._plan_type_rank("WEEKLY"), 1)
        self.assertGreater(final._plan_type_rank(None), 1)

    def test_default_plan_type_order_has_no_default_entry(self):
        self.assertEqual(final.DEFAULT_PLAN_TYPE_ORDER, ("DAILY", "ON-TOP-FOOD"))
        with patch.object(final, "FINAL_DECISION_PLAN_TYPE_ORDER", ""):
            self.assertEqual(final._plan_type_order(), ["DAILY", "ON-TOP-FOOD"])
            self.assertGreater(final._plan_type_rank("default"), 1)

    def test_cities_are_listed_by_city_group(self):
        data = self.read(incentive_date=DATE)

        self.assertEqual(data["group_order"], ["Tehran Group", "Top 4", "Tier 1", "Tier 2", "Tier 3"])
        # Tehran Group first (matched through "tehran-group"), then Top 4
        # (matched through "TOP_4"), the listed tiers, Tier 4, and finally the
        # remaining groups / unknown group alphabetically.
        self.assertEqual(
            [(c["city"], c["city_group"]) for c in data["cities"]],
            [
                ("karaj", "tehran-group"),
                ("tehran", "Top 4"),
                ("tabriz", "TOP_4"),
                ("isfahan", "Tier-1"),
                ("kerman", "Tier 2"),
                ("qom", "Tier 3"),
                ("ahvaz", "Tier 4"),
                ("mashhad", "Zone X"),
                ("rasht", None),
            ],
        )

    def test_group_sort_key_ignores_case_and_separators(self):
        key = final._group_sort_key
        self.assertEqual(key("TEHRAN GROUP")[0], 0)
        self.assertEqual(key("tehran-group"), key("Tehran Group"))
        self.assertEqual(key("Tehran"), key("Tehran Group"))
        self.assertEqual(key("TOP_4"), key("Top 4"))
        self.assertEqual(key("top-4"), key("Top 4"))
        self.assertEqual(key("tier1"), key("Tier 1"))
        # an unlisted tier follows the configured ones, in numeric order
        self.assertEqual(key("Tier 4")[0], 1)
        self.assertLess(key("Tier 4"), key("Tier 10"))
        # everything else (and a missing group) comes last
        self.assertEqual(key("Zone X")[0], 2)
        self.assertGreater(key(None), key("Zone X"))

    def test_control_bucket_decoding(self):
        self.assertEqual(final._control_bucket("[0.2, 0.2, 0.1]"), [0.2, 0.2, 0.1])
        self.assertEqual(final._control_bucket([0.1, 0.2, 0.3]), [0.1, 0.2, 0.3])
        self.assertIsNone(final._control_bucket(None))
        self.assertIsNone(final._control_bucket("   "))
        # legacy scalars stay readable instead of turning into nothing
        self.assertEqual(final._control_bucket("0.25"), 0.25)
        self.assertEqual(final._control_bucket("auto"), "auto")


if __name__ == "__main__":
    unittest.main()
