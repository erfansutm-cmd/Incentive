"""API tests for the plan base-config lookup and its change log.

The SQL runs for real against an isolated SQLite store with attached
``incentive`` schema; SHOW COLUMNS is supplied as fixture metadata and MySQL's
NOW() is stubbed, so no configured database is ever touched.
Run: python -m unittest discover -s tests -v
"""

import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from app.api import incentive_base_configs as base_configs
from app.main import app

BASE = "/api/incentive-base-configs"
TABLE_SQL = "`incentive`.`incentive_base_configs`"
LOG_TABLE_SQL = "`incentive`.`incentive_base_configs_logs`"
NOW = "2026-09-14T10:11:16"


def column(name, kind="varchar(100)", nullable=True, default=None, key=""):
    return {
        "Field": name, "Type": kind, "Null": "YES" if nullable else "NO",
        "Key": key, "Default": default,
        "Extra": "auto_increment" if key == "PRI" else "",
    }


COLUMNS = [
    column("id", "bigint unsigned", nullable=False, key="PRI"),
    column("plan_id", "bigint unsigned", nullable=False),
    column("listing_id"), column("allocator_id"), column("rule_name"),
    column("impact_ratio", "decimal(10,4)"), column("duration", "int"),
    column("districts"), column("vendors"), column("batch_size", "int"),
    column("clustering_method"), column("sensitivity_id"), column("sensitivity_group"),
    column("created_at", "datetime"), column("updated_at", "datetime"),
    column("deactivated_at", "datetime"),
]

LOG_COLUMNS = [
    column("log_id", "bigint unsigned", nullable=False, key="PRI"),
    column("config_id", "bigint unsigned", nullable=False),
] + [copy.deepcopy(c) for c in COLUMNS[1:]] + [column("changed_at", "datetime")]
# the copied `id` column of the config is not part of the log table
LOG_COLUMNS = [c for c in LOG_COLUMNS if c["Field"] != "id"]

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
        clustering_method TEXT, sensitivity_id TEXT, sensitivity_group TEXT,
        created_at TEXT, updated_at TEXT, deactivated_at TEXT
    )
"""

CREATE_LOG_TABLE = f"""
    CREATE TABLE {LOG_TABLE_SQL} (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT, config_id INTEGER NOT NULL,
        plan_id INTEGER, listing_id TEXT, allocator_id TEXT, rule_name TEXT,
        impact_ratio REAL, duration INTEGER, districts TEXT, vendors TEXT,
        batch_size INTEGER, clustering_method TEXT, sensitivity_id TEXT,
        sensitivity_group TEXT, created_at TEXT, updated_at TEXT,
        deactivated_at TEXT, changed_at TEXT
    )
"""

INSERT = f"""
    INSERT INTO {TABLE_SQL} (
        id, plan_id, listing_id, allocator_id, rule_name, impact_ratio, duration,
        districts, vendors, batch_size, clustering_method, sensitivity_id,
        sensitivity_group, created_at
    ) VALUES (
        :id, :plan_id, :listing_id, :allocator_id, :rule_name, :impact_ratio,
        :duration, :districts, :vendors, :batch_size, :clustering_method,
        :sensitivity_id, :sensitivity_group, :created_at
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
        "created_at": "2026-09-05T10:00:00",
    })
    row.update(overrides)
    return row


class BaseConfigAPITests(unittest.TestCase):
    def setUp(self):
        self.columns = copy.deepcopy(COLUMNS)
        self.log_columns = copy.deepcopy(LOG_COLUMNS)
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def register_mysql_functions(conn, _):
            conn.create_function("NOW", 0, lambda: NOW)

        with self.engine.begin() as conn:
            conn.execute(text("ATTACH DATABASE ':memory:' AS incentive"))
            conn.execute(text(CREATE_TABLE))
            conn.execute(text(CREATE_LOG_TABLE))
            conn.execute(text(INSERT), [sample_row(v) for v in SAMPLES])

        for name, value in {
            "engine": self.engine, "TABLE_SQL": TABLE_SQL, "LOG_TABLE_SQL": LOG_TABLE_SQL,
        }.items():
            patcher = patch.object(base_configs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, source in {"_columns": "columns", "_log_columns": "log_columns"}.items():
            patcher = patch.object(
                base_configs, name, side_effect=lambda source=source: copy.deepcopy(getattr(self, source))
            )
            patcher.start()
            self.addCleanup(patcher.stop)

        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    # --- helpers ---------------------------------------------------------
    def read(self, plan_id, **params):
        response = self.client.get(BASE, params={"plan_id": plan_id, **params})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def logs(self, config_id):
        response = self.client.get(f"{BASE}/{config_id}/logs")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def sql(self, statement, **params):
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(statement), params)]

    def log_rows(self):
        return self.sql(f"SELECT * FROM {LOG_TABLE_SQL} ORDER BY log_id")

    def insert(self, **overrides):
        row = sample_row((99, 1, "listing", "allocator", "rule", 0.5), **overrides)
        with self.engine.begin() as conn:
            conn.execute(text(INSERT), row)
        return row

    # --- reading ---------------------------------------------------------
    def test_allocators_of_a_plan_are_listed_with_the_dominant_ratio_first(self):
        data = self.read(1)
        self.assertEqual(data["plan_id"], "1")
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(
            [(r["impact_ratio"], r["allocator_id"]) for r in data["rows"]],
            [
                (0.6, "foodZooket-kerman-3T-range-base-20260905"),
                (0.4, "foodZooket-kerman-3T-range-base"),
            ],
        )
        self.assertEqual({r["listing_id"] for r in data["rows"]}, {"kerman-daily-foodZooket"})
        self.assertEqual(data["impact_ratio_sum"], 1.0)
        self.assertEqual((data["total"], data["active_count"], data["deactivated_count"]), (2, 2, 0))

    def test_response_reports_the_summary_columns_and_the_full_table(self):
        data = self.read(1)
        self.assertEqual(
            data["summary_columns"], ["listing_id", "allocator_id", "rule_name", "impact_ratio"]
        )
        self.assertEqual([c["name"] for c in data["columns"]], [c["Field"] for c in COLUMNS])
        self.assertEqual(data["columns"][5]["type"], "decimal(10,4)")

    def test_single_allocator_plan_returns_every_column_of_its_row(self):
        data = self.read(3)
        self.assertEqual(len(data["rows"]), 1)
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
        # lifecycle columns come back verbatim; the UI formats them
        self.assertEqual(row["created_at"], "2026-09-05T10:00:00")
        self.assertIsNone(row["updated_at"])
        self.assertIsNone(row["deactivated_at"])

    def test_only_the_rows_of_the_requested_plan_are_returned(self):
        for plan_id, expected in [(4, 2), (7, 2), (10, 2), (2, 1), (8, 1)]:
            with self.subTest(plan_id=plan_id):
                data = self.read(plan_id)
                self.assertEqual(len(data["rows"]), expected)
                self.assertEqual({r["plan_id"] for r in data["rows"]}, {plan_id})

    def test_plan_without_configs_returns_an_empty_list(self):
        data = self.read(999)
        self.assertEqual(data["rows"], [])
        self.assertEqual((data["total"], data["active_count"]), (0, 0))
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
        self.assertEqual(len(self.read(" 1 ")["rows"]), 2)

    def test_impact_ratio_sum_ignores_missing_ratios(self):
        self.insert(id=100, plan_id=42, impact_ratio=None)
        self.insert(id=101, plan_id=42, impact_ratio=0.25)
        data = self.read(42)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["impact_ratio_sum"], 0.25)

    def test_deactivated_configs_are_hidden_until_asked_for(self):
        with self.engine.begin() as conn:
            conn.execute(text(f"UPDATE {TABLE_SQL} SET deactivated_at = :at WHERE id = 2"), {"at": NOW})
        active = self.read(1)
        self.assertEqual([r["id"] for r in active["rows"]], [1])
        self.assertEqual((active["total"], active["active_count"], active["deactivated_count"]), (2, 1, 1))
        # the plan's share is summed over its active allocators only
        self.assertEqual(active["impact_ratio_sum"], 0.4)

        everything = self.read(1, include_deactivated="true")
        self.assertTrue(everything["include_deactivated"])
        self.assertEqual([r["id"] for r in everything["rows"]], [2, 1])
        self.assertEqual(everything["deactivated_count"], 1)
        self.assertEqual(everything["impact_ratio_sum"], 0.4)

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

    def test_missing_table_maps_to_a_404_message(self):
        exc = Exception("wrapped")
        exc.orig = Exception(1146, "Table 'incentive.incentive_base_configs' doesn't exist")
        status, message = base_configs._failure(exc)
        self.assertEqual(status, 404)
        self.assertIn("incentive/incentive_base_configs", message)

    # --- writing: the previous row is logged first ------------------------
    def test_update_logs_the_previous_row_and_applies_the_change(self):
        response = self.client.put(f"{BASE}/2", json={"impact_ratio": "0.75", "batch_size": 5})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["logged"])
        self.assertEqual(body["log_id"], 1)
        self.assertEqual(body["changes"], {
            "impact_ratio": {"from": 0.6, "to": 0.75},
            "batch_size": {"from": 0, "to": 5},
        })
        self.assertEqual(body["row"]["impact_ratio"], 0.75)
        self.assertEqual(body["row"]["updated_at"], NOW)
        self.assertEqual(body["row"]["created_at"], "2026-09-05T10:00:00")

        logged = self.log_rows()
        self.assertEqual(len(logged), 1)
        # the log holds the row as it was *before* the change
        self.assertEqual(logged[0]["config_id"], 2)
        self.assertEqual(logged[0]["plan_id"], 1)
        self.assertEqual(logged[0]["impact_ratio"], 0.6)
        self.assertEqual(logged[0]["batch_size"], 0)
        self.assertEqual(logged[0]["rule_name"], "foodZooket-kerman-3step-base-20260616")
        self.assertEqual(logged[0]["created_at"], "2026-09-05T10:00:00")
        self.assertIsNone(logged[0]["updated_at"])
        self.assertEqual(logged[0]["changed_at"], NOW)
        # …and the config itself moved on
        self.assertEqual(self.read(1)["rows"][0]["impact_ratio"], 0.75)

    def test_unchanged_values_are_not_logged(self):
        response = self.client.put(f"{BASE}/2", json={"impact_ratio": "0.6000", "rule_name": "foodZooket-kerman-3step-base-20260616"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["logged"])
        self.assertEqual(body["changes"], {})
        self.assertEqual(body["message"], "No changes to record.")
        self.assertEqual(self.log_rows(), [])

    def test_every_change_appends_its_own_log_row(self):
        self.client.put(f"{BASE}/5", json={"impact_ratio": 0.7})
        self.client.put(f"{BASE}/5", json={"clustering_method": "dbscan"})
        logged = self.log_rows()
        self.assertEqual([r["impact_ratio"] for r in logged], [0.8, 0.7])
        self.assertEqual([r["clustering_method"] for r in logged], ["kmeans", "kmeans"])
        self.assertEqual({r["config_id"] for r in logged}, {5})

    def test_managed_columns_cannot_be_set_through_update(self):
        response = self.client.put(f"{BASE}/2", json={
            "id": 999, "plan_id": 42, "created_at": "2000-01-01T00:00:00",
            "deactivated_at": "2000-01-01T00:00:00", "rule_name": "renamed",
            "not_a_column": "x",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(list(response.json()["changes"]), ["rule_name"])
        row = self.read(1)["rows"][0]
        self.assertEqual(row["id"], 2)
        self.assertEqual(row["plan_id"], 1)
        self.assertEqual(row["created_at"], "2026-09-05T10:00:00")
        self.assertIsNone(row["deactivated_at"])
        self.assertEqual(row["rule_name"], "renamed")

    def test_update_rejects_an_empty_or_unknown_payload(self):
        for payload in [{}, {"not_a_column": "x"}, {"created_at": "2000-01-01T00:00:00"}]:
            with self.subTest(payload=payload):
                response = self.client.put(f"{BASE}/2", json=payload)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("No valid fields", response.json()["message"])
        self.assertEqual(self.log_rows(), [])

    def test_update_of_an_unknown_config_is_a_404_and_logs_nothing(self):
        response = self.client.put(f"{BASE}/999", json={"impact_ratio": 0.5})
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.log_rows(), [])

    def test_deactivate_logs_the_previous_row(self):
        response = self.client.post(f"{BASE}/1/deactivate")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["logged"])
        self.assertFalse(body["active"])

        logged = self.log_rows()
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]["config_id"], 1)
        self.assertEqual(logged[0]["impact_ratio"], 0.4)
        self.assertIsNone(logged[0]["deactivated_at"])  # it was active before
        self.assertEqual(logged[0]["changed_at"], NOW)

        # the config is now deactivated, so it drops out of the default listing
        self.assertEqual([r["id"] for r in self.read(1)["rows"]], [2])
        self.assertEqual(self.read(1, include_deactivated="true")["deactivated_count"], 1)
        self.assertEqual(
            self.sql(f"SELECT deactivated_at, updated_at FROM {TABLE_SQL} WHERE id = 1")[0],
            {"deactivated_at": NOW, "updated_at": NOW},
        )

    def test_deactivating_twice_keeps_the_first_log_row(self):
        self.client.post(f"{BASE}/1/deactivate")
        response = self.client.post(f"{BASE}/1/deactivate")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["logged"])
        self.assertEqual(body["message"], "Base config is already deactivated.")
        self.assertEqual(len(self.log_rows()), 1)

    def test_deactivate_of_an_unknown_config_is_a_404(self):
        self.assertEqual(self.client.post(f"{BASE}/999/deactivate").status_code, 404)
        self.assertEqual(self.log_rows(), [])

    def test_writes_fail_cleanly_without_the_log_table(self):
        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {LOG_TABLE_SQL}"))
        response = self.client.put(f"{BASE}/2", json={"impact_ratio": 0.9})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("no such table", response.json()["message"])
        # nothing was applied and no history was lost silently
        self.assertEqual(self.read(1)["rows"][0]["impact_ratio"], 0.6)

    def test_writes_need_a_config_id_in_the_log_table(self):
        self.log_columns = [c for c in self.log_columns if c["Field"] != "config_id"]
        response = self.client.put(f"{BASE}/2", json={"impact_ratio": 0.9})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("config_id", response.json()["message"])
        self.assertEqual(self.read(1)["rows"][0]["impact_ratio"], 0.6)

    # --- reading the log -------------------------------------------------
    def test_logs_are_listed_newest_first_for_their_config_only(self):
        self.client.put(f"{BASE}/5", json={"impact_ratio": 0.7})
        self.client.put(f"{BASE}/5", json={"impact_ratio": 0.9})
        self.client.put(f"{BASE}/6", json={"impact_ratio": 0.3})

        data = self.logs(5)
        self.assertEqual(data["config_id"], "5")
        self.assertEqual(data["total"], 2)
        self.assertEqual([r["impact_ratio"] for r in data["rows"]], [0.7, 0.8])
        self.assertEqual([r["log_id"] for r in data["rows"]], [2, 1])
        self.assertEqual([r["changed_at"] for r in data["rows"]], [NOW, NOW])
        self.assertEqual(data["columns"][0]["name"], "log_id")
        self.assertEqual(self.logs(6)["total"], 1)
        self.assertEqual(self.logs(7)["rows"], [])

    def test_logs_of_an_unknown_config_are_an_empty_list(self):
        data = self.logs(12345)
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(len(data["columns"]), len(LOG_COLUMNS))

    def test_reading_logs_reports_a_missing_log_table(self):
        with self.engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {LOG_TABLE_SQL}"))
        response = self.client.get(f"{BASE}/5/logs")
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("no such table", response.json()["message"])
