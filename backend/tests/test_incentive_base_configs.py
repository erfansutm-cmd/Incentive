"""API tests for the plan base-config lookup, against an isolated SQLite store.

The SELECT runs for real with an attached ``incentive`` schema; SHOW COLUMNS is
supplied as fixture metadata, so no configured database is ever touched.
Run: python -m unittest discover -s tests -v
"""

import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.api import incentive_base_configs as base_configs
from app.main import app

BASE = "/api/incentive-base-configs"
TABLE_SQL = "`incentive`.`incentive_base_configs`"


def column(name, kind="varchar(100)", nullable=True, default=None):
    return {
        "Field": name, "Type": kind, "Null": "YES" if nullable else "NO",
        "Key": "PRI" if name == "id" else "", "Default": default,
        "Extra": "auto_increment" if name == "id" else "",
    }


COLUMNS = [
    column("id", "bigint unsigned", nullable=False),
    column("plan_id", "bigint unsigned", nullable=False),
    column("listing_id"), column("allocator_id"), column("rule_name"),
    column("impact_ratio", "decimal(10,4)"), column("duration", "int"),
    column("districts"), column("vendors"), column("batch_size", "int"),
    column("clustering_method"), column("sensitivity_id"), column("sensitivity_group"),
]

# incentive.incentive_base_configs sample rows, in table order:
#   id | plan_id | listing_id | allocator_id | rule_name | impact_ratio
SAMPLES = [
    (1, 1, "kerman-daily-foodZooket", "foodZooket-kerman-3T-range-base",
     "foodZooket-kerman-3step-base", 0.4),
    (2, 1, "kerman-daily-foodZooket", "foodZooket-kerman-3T-range-base-20260905",
     "foodZooket-kerman-3step-base-20260616", 0.6),
    (3, 2, "shiraz-daily-foodZooket", "foodZooket-shiraz-2T-base-20260617",
     "foodZooket-shiraz-2step-base", 1.0),
    (4, 3, "kish-daily-foodZooket", "foodZooket-kish-1T-base",
     "foodZooket-kish-1step-base", 1.0),
    (5, 4, "semnan-foodzooket-60d", "foodZooket-semnan-1T-base",
     "foodZooket-semnan-1step-base", 0.8),
    (6, 4, "semnan-foodzooket-60d", "foodZooket-semnan-1T-base-2",
     "foodZooket-semnan-1step-base-20PerExtra", 0.2),
    (7, 5, "yasouj-foodzooket-60d", "foodZooket-yasouj-1T-base",
     "foodZooket-yasouj-1step-base", 1.0),
    (8, 6, "maraghe-foodzooket-60d", "foodZooket-maraghe-1T-base",
     "foodZooket-maraghe-1step-base", 1.0),
    (9, 7, "kordestan-foodzooket-60d", "foodZooket-kordestan-1T-base",
     "foodZooket-kordestan-1step-base", 0.8),
    (10, 7, "kordestan-foodzooket-60d", "foodZooket-kordestan-1T-base-2",
     "foodZooket-kordestan-1step-base-20PerExtra", 0.2),
    (11, 8, "arak-daily-foodZooket", "foodZooket-arak-2T-base-20260729",
     "foodZooket-arak-2step-base-20260729", 1.0),
    (12, 9, "hormozgan-daily-foodZooket", "foodZooket-hormozgan-2T-base",
     "foodZooket-hormozgan-1step-base", 0.6),
    (13, 9, "hormozgan-daily-foodZooket", "foodZooket-hormozgan-3T-base-20260616",
     "foodZooket-hormozgan-3step-base-20260616", 0.4),
    (14, 10, "bushehr-daily-foodZooket", "foodZooket-bushehr-2T-base",
     "foodZooket-bushehr-2step-base", 0.8),
    (15, 10, "bushehr-daily-foodZooket", "foodZooket-bushehr-2T-base-20260617",
     "foodZooket-bushehr-2step-base-20260617", 0.2),
]

CREATE_TABLE = f"""
    CREATE TABLE {TABLE_SQL} (
        id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL,
        listing_id TEXT, allocator_id TEXT, rule_name TEXT, impact_ratio REAL,
        duration INTEGER, districts TEXT, vendors TEXT, batch_size INTEGER,
        clustering_method TEXT, sensitivity_id TEXT, sensitivity_group TEXT
    )
"""

INSERT = f"""
    INSERT INTO {TABLE_SQL} (
        id, plan_id, listing_id, allocator_id, rule_name, impact_ratio, duration,
        districts, vendors, batch_size, clustering_method, sensitivity_id,
        sensitivity_group
    ) VALUES (
        :id, :plan_id, :listing_id, :allocator_id, :rule_name, :impact_ratio,
        :duration, :districts, :vendors, :batch_size, :clustering_method,
        :sensitivity_id, :sensitivity_group
    )
"""


def sample_row(values, **overrides):
    """A full sample row: the shared tail is duration/districts/…/kmeans/''/''."""
    row = dict(zip(
        ("id", "plan_id", "listing_id", "allocator_id", "rule_name", "impact_ratio"),
        values,
    ))
    row.update({
        "duration": 1, "districts": "", "vendors": "", "batch_size": 0,
        "clustering_method": "kmeans", "sensitivity_id": "", "sensitivity_group": "",
    })
    row.update(overrides)
    return row


class BaseConfigAPITests(unittest.TestCase):
    def setUp(self):
        self.columns = copy.deepcopy(COLUMNS)
        self.create_sql = CREATE_TABLE
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        with self.engine.begin() as conn:
            conn.execute(text("ATTACH DATABASE ':memory:' AS incentive"))
            conn.execute(text(self.create_sql))
            conn.execute(text(INSERT), [sample_row(v) for v in SAMPLES])

        for name, value in {"engine": self.engine, "TABLE_SQL": TABLE_SQL}.items():
            patcher = patch.object(base_configs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(base_configs, "_columns", side_effect=lambda: copy.deepcopy(self.columns))
        patcher.start()
        self.addCleanup(patcher.stop)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    def read(self, plan_id):
        response = self.client.get(BASE, params={"plan_id": plan_id})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def insert(self, **overrides):
        row = sample_row((99, 1, "listing", "allocator", "rule", 0.5), **overrides)
        with self.engine.begin() as conn:
            conn.execute(text(INSERT), row)
        return row

    def test_allocators_of_a_plan_are_listed_with_the_dominant_ratio_first(self):
        data = self.read(1)
        self.assertEqual(data["plan_id"], "1")
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            [(r["impact_ratio"], r["allocator_id"]) for r in data["rows"]],
            [
                (0.6, "foodZooket-kerman-3T-range-base-20260905"),
                (0.4, "foodZooket-kerman-3T-range-base"),
            ],
        )
        # Both rows belong to the same listing, so they stay adjacent.
        self.assertEqual({r["listing_id"] for r in data["rows"]}, {"kerman-daily-foodZooket"})
        self.assertEqual(data["impact_ratio_sum"], 1.0)

    def test_response_reports_the_summary_columns_and_the_full_table(self):
        data = self.read(1)
        self.assertEqual(
            data["summary_columns"], ["listing_id", "allocator_id", "rule_name", "impact_ratio"]
        )
        self.assertEqual([c["name"] for c in data["columns"]], [c["Field"] for c in COLUMNS])
        self.assertEqual(data["columns"][5]["type"], "decimal(10,4)")

    def test_single_allocator_plan_returns_every_column_of_its_row(self):
        data = self.read(3)
        self.assertEqual(data["total"], 1)
        row = data["rows"][0]
        self.assertEqual(row["id"], 4)
        self.assertEqual(row["listing_id"], "kish-daily-foodZooket")
        self.assertEqual(row["allocator_id"], "foodZooket-kish-1T-base")
        self.assertEqual(row["rule_name"], "foodZooket-kish-1step-base")
        self.assertEqual(row["impact_ratio"], 1.0)
        self.assertEqual(row["duration"], 1)
        self.assertEqual(row["batch_size"], 0)
        self.assertEqual(row["clustering_method"], "kmeans")
        self.assertEqual(row["districts"], "")
        self.assertEqual(row["vendors"], "")
        self.assertEqual(row["sensitivity_id"], "")
        self.assertEqual(row["sensitivity_group"], "")

    def test_only_the_rows_of_the_requested_plan_are_returned(self):
        for plan_id, expected in [(4, 2), (7, 2), (10, 2), (2, 1), (8, 1)]:
            with self.subTest(plan_id=plan_id):
                data = self.read(plan_id)
                self.assertEqual(data["total"], expected)
                self.assertEqual({r["plan_id"] for r in data["rows"]}, {plan_id})

    def test_plan_without_configs_returns_an_empty_list(self):
        data = self.read(999)
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["total"], 0)
        self.assertIsNone(data["impact_ratio_sum"])
        # The columns are still reported, so the UI can render its headers.
        self.assertEqual(len(data["columns"]), len(COLUMNS))

    def test_plan_id_is_required(self):
        for params in [{}, {"plan_id": ""}, {"plan_id": "   "}]:
            with self.subTest(params=params):
                response = self.client.get(BASE, params=params)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["status"], "error")
                self.assertIn("plan_id", response.json()["message"])

    def test_plan_id_matches_on_its_string_value(self):
        # The UI passes the route param as text; the join must still match.
        self.assertEqual(self.read(" 1 ")["total"], 2)

    def test_impact_ratio_sum_ignores_missing_ratios(self):
        self.insert(id=100, plan_id=42, impact_ratio=None)
        self.insert(id=101, plan_id=42, impact_ratio=0.25)
        data = self.read(42)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["impact_ratio_sum"], 0.25)

    def test_missing_table_is_reported_as_an_error_response(self):
        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {TABLE_SQL}"))
        response = self.client.get(BASE, params={"plan_id": 1})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("no such table", response.json()["message"])

    def test_missing_plan_id_column_is_reported_as_a_bad_request(self):
        self.columns = [c for c in self.columns if c["Field"] != "plan_id"]
        response = self.client.get(BASE, params={"plan_id": 1})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("plan_id", response.json()["message"])

    def test_summary_columns_skip_columns_the_table_does_not_have(self):
        self.columns = [c for c in self.columns if c["Field"] != "rule_name"]
        self.assertEqual(
            self.read(1)["summary_columns"], ["listing_id", "allocator_id", "impact_ratio"]
        )

    def test_rows_are_ordered_by_listing_then_ratio_when_there_is_no_ratio(self):
        self.columns = [c for c in self.columns if c["Field"] != "impact_ratio"]
        data = self.read(1)
        self.assertEqual(
            [r["allocator_id"] for r in data["rows"]],
            ["foodZooket-kerman-3T-range-base", "foodZooket-kerman-3T-range-base-20260905"],
        )
        self.assertIsNone(data["impact_ratio_sum"])

    def test_deactivated_configs_are_hidden_when_the_table_has_the_column(self):
        # Re-create the table with a lifecycle column, like the other tables.
        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {TABLE_SQL}"))
            conn.execute(text(self.create_sql.replace("sensitivity_group TEXT", "sensitivity_group TEXT, deactivated_at TEXT")))
            conn.execute(text(INSERT), [sample_row(v) for v in SAMPLES[:2]])
            conn.execute(text(f"UPDATE {TABLE_SQL} SET deactivated_at = '2026-09-01 00:00:00' WHERE id = 2"))
        self.columns.append(column("deactivated_at", "datetime"))
        data = self.read(1)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["rows"][0]["id"], 1)
        self.assertEqual(data["impact_ratio_sum"], 0.4)

    def test_missing_table_maps_to_a_404_message(self):
        exc = Exception("wrapped")
        exc.orig = Exception(1146, "Table 'incentive.incentive_base_configs' doesn't exist")
        status, message = base_configs._failure(exc)
        self.assertEqual(status, 404)
        self.assertIn("incentive/incentive_base_configs", message)
