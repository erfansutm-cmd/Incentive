"""API tests against an isolated SQLite store; never touch the configured DB.

The CRUD SQL runs for real with attached incentive/mafsho schemas. SHOW COLUMNS
is supplied as fixture metadata and MySQL NOW/GET_LOCK/RELEASE_LOCK are stubbed.
Separate tests verify the named-lock transaction lifecycle (not MySQL's lock
implementation). Run: python -m unittest discover -s tests -v
"""

import copy
import datetime
import decimal
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from app.api import decision_matrix as matrix
from app.main import app


def column(name, kind="varchar(100)", nullable=False, default=None):
    return {
        "Field": name, "Type": kind, "Null": "YES" if nullable else "NO",
        "Key": "PRI" if name == "id" else "", "Default": default,
        "Extra": "auto_increment" if name == "id" else "",
    }


COLUMNS = [
    column("id", "bigint unsigned"), column("incentive_type", "int"),
    column("city_group"), column("score_type"), column("score", "int unsigned"),
    column("target_increase", "decimal(10,4)"), column("pr_increase", "decimal(10,4)"),
    column("control_bucket", "int unsigned", nullable=True),
    column("created_at", "datetime"), column("deactivated_at", "datetime", nullable=True),
]
BASE = "/api/decision-matrix"


class DecisionMatrixAPITests(unittest.TestCase):
    def setUp(self):
        self.now = "2026-09-08T12:00:00"
        self.lock_result = 1
        self.lock_events = []
        self.columns = copy.deepcopy(COLUMNS)
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def register_mysql_functions(conn, _):
            conn.create_function("NOW", 0, lambda: self.now)
            conn.create_function("GET_LOCK", 2, self.acquire_lock)
            conn.create_function("RELEASE_LOCK", 1, self.release_lock)

        @event.listens_for(self.engine, "commit")
        def record_commit(_):
            self.lock_events.append("commit")

        with self.engine.begin() as conn:
            conn.execute(text("ATTACH DATABASE ':memory:' AS incentive"))
            conn.execute(text("ATTACH DATABASE ':memory:' AS mafsho"))
            conn.execute(text("CREATE TABLE incentive.incentive_active_city (city_group TEXT COLLATE NOCASE)"))
            conn.execute(text("CREATE TABLE mafsho.incentive_type (id INTEGER PRIMARY KEY, name TEXT)"))
            conn.execute(text("INSERT INTO mafsho.incentive_type VALUES (1, 'DAILY'), (2, 'WEEKLY')"))
            conn.execute(text("INSERT INTO incentive.incentive_active_city VALUES (:group)"), [
                {"group": value} for value in ["Group A", "Group A", "Group B", "O'Hare / A&B", None, "", "   "]
            ])
            conn.execute(text("""
                CREATE TABLE incentive.incentive_decision_matrix (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, incentive_type INTEGER NOT NULL,
                    city_group TEXT COLLATE NOCASE NOT NULL, score_type TEXT COLLATE NOCASE NOT NULL,
                    score INTEGER NOT NULL, target_increase NUMERIC NOT NULL, pr_increase NUMERIC NOT NULL,
                    control_bucket INTEGER, created_at TEXT NOT NULL, deactivated_at TEXT
                )
            """))
        self.lock_events.clear()
        for name, value in {
            "engine": self.engine,
            "TABLE_SQL": "`incentive`.`incentive_decision_matrix`",
            "ACTIVE_CITY_SQL": "`incentive`.`incentive_active_city`",
            "INCENTIVE_TYPE_SQL": "`mafsho`.`incentive_type`",
        }.items():
            patcher = patch.object(matrix, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(matrix, "_columns", side_effect=lambda conn: copy.deepcopy(self.columns))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    def acquire_lock(self, name, timeout):
        self.assertEqual(name, matrix.WRITE_LOCK)
        self.assertLessEqual(len(name), 64)
        self.assertEqual(timeout, 5)
        self.lock_events.append("acquire")
        return self.lock_result

    def release_lock(self, name):
        self.assertEqual(name, matrix.WRITE_LOCK)
        self.lock_events.append("release")
        return 1

    def add(self, **overrides):
        payload = {
            "city_group": "Group A", "incentive_type": 1, "score_type": "Delivery",
            "target_increase": "0.125", "pr_increase": "1.75", "control_bucket": 0,
            **overrides,
        }
        return self.client.post(BASE, json=payload)

    def read(self, city_group="Group A", **params):
        response = self.client.get(BASE, params={"city_group": city_group, **params})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_empty_matrix_still_lists_distinct_nonblank_source_groups(self):
        response = self.client.get(f"{BASE}/city-groups")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rows"], [
            {"city_group": "Group A"}, {"city_group": "Group B"}, {"city_group": "O'Hare / A&B"},
        ])
        data = self.read()
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["series"], [])
        self.assertEqual(len(data["columns"]), 10)
        self.assertEqual(data["columns"][5]["type"], "decimal(10,4)")

    def test_first_step_stores_type_id_values_and_managed_timestamps(self):
        response = self.add(score=1)
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()["row"]
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["incentive_type"], 1)
        self.assertEqual(row["score"], 1)
        self.assertEqual(row["target_increase"], 0.125)
        self.assertEqual(row["pr_increase"], 1.75)
        self.assertEqual(row["control_bucket"], 0)
        self.assertEqual(row["created_at"], self.now)
        self.assertIsNone(row["deactivated_at"])
        data = self.read()
        self.assertEqual(data["rows"][0]["incentive_type_name"], "DAILY")
        self.assertEqual(data["series"][0]["next_score"], 2)
        self.assertEqual(self.lock_events, ["acquire", "commit", "release", "commit"])

    def test_each_hierarchy_combination_has_its_own_sequence(self):
        for overrides, score in [
            ({}, 1), ({}, 2), ({"city_group": "Group B"}, 1),
            ({"incentive_type": 2}, 1), ({"score_type": "Quality"}, 1), ({}, 3),
        ]:
            response = self.add(**overrides)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["row"]["score"], score)
        self.assertEqual(len(self.read("Group B")["rows"]), 1)
        self.assertEqual(len(self.read()["series"]), 3)

    def test_scores_are_not_reused_or_renumbered_after_deactivation(self):
        ids = [self.add().json()["row"]["id"] for _ in range(3)]
        self.client.post(f"{BASE}/{ids[1]}/deactivate")
        self.client.post(f"{BASE}/{ids[2]}/deactivate")
        data = self.read()
        self.assertEqual([row["score"] for row in data["rows"]], [1])
        self.assertEqual(data["series"][0]["next_score"], 4)
        self.assertEqual(data["series"][0]["deactivated_count"], 2)
        self.assertEqual(self.add(score=4).json()["row"]["score"], 4)
        all_rows = self.read(include_deactivated=True)["rows"]
        self.assertEqual([row["score"] for row in all_rows], [1, 2, 3, 4])
        self.assertIsNotNone(all_rows[1]["deactivated_at"])

    def test_all_deactivated_series_remains_discoverable(self):
        row = self.add().json()["row"]
        self.client.post(f"{BASE}/{row['id']}/deactivate")
        data = self.read()
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["series"], [{
            "incentive_type": 1, "score_type": "Delivery", "next_score": 2,
            "active_count": 0, "deactivated_count": 1,
        }])
        self.assertEqual(self.add().json()["row"]["score"], 2)

    def test_stale_or_skipped_score_is_rejected_without_an_insert(self):
        self.assertEqual(self.add(score=3).status_code, 409)
        self.assertEqual(self.add(score=1).status_code, 200)
        stale = self.add(score=1)
        self.assertEqual(stale.status_code, 409)
        self.assertIn("next score for this score type is 2", stale.json()["message"])
        self.assertEqual(len(self.read()["rows"]), 1)

    def test_case_insensitive_series_keeps_original_name(self):
        self.add(score_type="Delivery")
        response = self.add(score_type="delivery", city_group="group a", score=2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["row"]["score_type"], "Delivery")
        self.assertEqual(response.json()["row"]["city_group"], "Group A")
        self.assertEqual(len(self.read()["series"]), 1)

    def test_only_existing_lookup_values_can_be_used(self):
        for overrides in [{"city_group": "Not a group"}, {"incentive_type": 999}, {"incentive_type": "DAILY"}]:
            with self.subTest(overrides=overrides):
                response = self.add(**overrides)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.read()["rows"], [])
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM mafsho.incentive_type")).scalar(), 2)

    def test_input_validation(self):
        invalid = [
            {"score_type": "  "}, {"city_group": []}, {"score_type": {}},
            {"incentive_type": True}, {"incentive_type": "1junk"}, {"incentive_type": 1.5},
            {"score": 0}, {"score": -1}, {"score": 1.5}, {"score": True}, {"score": "NaN"},
            {"target_increase": "no"}, {"target_increase": "NaN"}, {"pr_increase": "Infinity"},
            {"target_increase": []}, {"pr_increase": True}, {"target_increase": ""},
            {"control_bucket": 1.5}, {"control_bucket": -1}, {"score_type": "a" * 101},
        ]
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                response = self.add(**overrides)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.read()["rows"], [])

    def test_managed_and_unknown_fields_are_not_writable(self):
        for field in ["id", "created_at", "deactivated_at", "incentive_type_name", "unexpected"]:
            with self.subTest(field=field):
                self.assertEqual(self.add(**{field: "anything"}).status_code, 400)
        self.assertEqual(self.read()["rows"], [])

    def test_nullability_defaults_and_text_control_bucket_follow_schema(self):
        self.columns[6]["Default"] = "0"
        self.columns[7]["Type"] = "varchar(30)"
        response = self.add(pr_increase="", control_bucket="holdout-A")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["row"]["pr_increase"], 0)
        self.assertEqual(response.json()["row"]["control_bucket"], "holdout-A")
        self.assertIsNone(self.add(control_bucket=None).json()["row"]["control_bucket"])

    def test_deactivation_is_idempotent_and_preserves_other_values(self):
        before = self.add().json()["row"]
        first = self.client.post(f"{BASE}/{before['id']}/deactivate")
        self.assertEqual(first.status_code, 200)
        timestamp = self.now
        self.now = "2026-09-09T13:00:00"
        second = self.client.post(f"{BASE}/{before['id']}/deactivate")
        self.assertEqual(second.status_code, 200)
        self.assertIn("already deactivated", second.json()["message"])
        after = self.read(include_deactivated=True)["rows"][0]
        self.assertEqual(after["deactivated_at"], timestamp)
        for key in ["id", "score", "created_at", "target_increase", "pr_increase", "control_bucket"]:
            self.assertEqual(before[key], after[key])
        self.assertEqual(self.client.post(f"{BASE}/999/deactivate").status_code, 404)

    def test_group_query_is_required_and_parameterized(self):
        self.assertEqual(self.client.get(BASE).status_code, 422)
        self.assertEqual(self.client.get(BASE, params={"city_group": "  "}).status_code, 400)
        response = self.add(city_group="O'Hare / A&B", score_type="x' OR 1=1 --")
        self.assertEqual(response.status_code, 200)
        data = self.read("O'Hare / A&B")
        self.assertEqual(data["rows"][0]["score_type"], "x' OR 1=1 --")
        self.assertEqual(self.read("Group A' OR 1=1 --")["rows"], [])
        self.assertEqual(self.add(city_group="Group A' OR 1=1 --").status_code, 400)

    def test_lock_timeout_returns_retryable_error_and_does_not_insert(self):
        self.lock_result = 0
        response = self.add()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.lock_events, ["acquire"])
        self.assertEqual(self.read()["rows"], [])

    def test_validation_error_rolls_back_and_releases_lock(self):
        self.assertEqual(self.add(incentive_type=999).status_code, 400)
        self.assertEqual(self.lock_events, ["acquire", "release", "commit"])
        self.assertEqual(self.add(score=1).status_code, 200)

    def test_schema_errors_have_actionable_response(self):
        with patch.object(matrix, "_columns", side_effect=matrix.MatrixError("Missing score column.")):
            response = self.client.get(BASE, params={"city_group": "Group A"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Missing score column.")


class HelperTests(unittest.TestCase):
    def test_serialization(self):
        self.assertEqual(matrix._jsonable(decimal.Decimal("0.125")), 0.125)
        self.assertEqual(matrix._jsonable(datetime.datetime(2026, 9, 8, 12)), "2026-09-08T12:00:00")
        self.assertEqual(matrix._jsonable(b"DAILY"), "DAILY")

    def test_schema_introspection_checks_required_columns(self):
        conn = MagicMock()
        conn.execute.return_value.mappings.return_value = COLUMNS[:-1]
        with self.assertRaisesRegex(matrix.MatrixError, "deactivated_at"):
            matrix._columns(conn)

    def test_failed_lock_release_discards_pooled_connection(self):
        conn = MagicMock()
        lock_result = MagicMock()
        lock_result.scalar.return_value = 1
        conn.execute.side_effect = [lock_result, RuntimeError("connection lost")]
        with patch.object(matrix, "engine") as engine, self.assertLogs(matrix.logger, level="ERROR"):
            engine.connect.return_value.__enter__.return_value = conn
            with matrix._write_transaction() as writer:
                self.assertIs(writer, conn)
        conn.invalidate.assert_called_once()
        conn.commit.assert_called_once()

    def test_unexpected_write_error_rolls_back_and_releases_lock(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 1
        with patch.object(matrix, "engine") as engine:
            engine.connect.return_value.__enter__.return_value = conn
            with self.assertRaisesRegex(RuntimeError, "insert failed"):
                with matrix._write_transaction():
                    raise RuntimeError("insert failed")
        conn.rollback.assert_called_once()
        self.assertIn("RELEASE_LOCK", str(conn.execute.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()
