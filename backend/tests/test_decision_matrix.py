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
    column("control_bucket", "json", nullable=True),
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
                    score INTEGER NOT NULL, target_increase REAL NOT NULL, pr_increase REAL NOT NULL,
                    control_bucket TEXT, created_at TEXT NOT NULL, deactivated_at TEXT
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
            "target_increase": "0.125", "pr_increase": "1.75", "control_bucket": None,
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
        self.assertIsNone(row["control_bucket"])
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

    def test_next_score_uses_active_rows_and_preserves_reused_score_history(self):
        ids = [self.add().json()["row"]["id"] for _ in range(3)]
        self.client.post(f"{BASE}/{ids[1]}/deactivate")
        self.client.post(f"{BASE}/{ids[2]}/deactivate")
        data = self.read()
        self.assertEqual([row["score"] for row in data["rows"]], [1])
        self.assertEqual(data["series"][0]["next_score"], 2)
        self.assertEqual(data["series"][0]["deactivated_count"], 2)
        self.assertEqual(self.read(include_deactivated=True)["series"][0]["next_score"], 2)
        self.now = "2026-09-08T14:00:00"
        replacement = self.add(score=2).json()["row"]
        self.assertEqual(replacement["score"], 2)
        self.assertNotIn(replacement["id"], ids)
        all_rows = self.read(include_deactivated=True)["rows"]
        self.assertEqual([row["score"] for row in all_rows], [1, 2, 2, 3])
        old = next(row for row in all_rows if row["id"] == ids[1])
        self.assertEqual(old["created_at"], "2026-09-08T12:00:00")
        self.assertIsNotNone(old["deactivated_at"])
        self.assertIsNone(replacement["deactivated_at"])
        self.assertEqual(self.read()["series"][0]["next_score"], 3)

    def test_deactivating_middle_score_does_not_duplicate_a_higher_active_score(self):
        ids = [self.add().json()["row"]["id"] for _ in range(3)]
        self.client.post(f"{BASE}/{ids[1]}/deactivate")
        self.assertEqual(self.read()["series"][0]["next_score"], 4)
        self.assertEqual(self.add(score=3).status_code, 409)
        self.assertEqual(self.add(score=4).status_code, 200)
        self.assertEqual([row["score"] for row in self.read()["rows"]], [1, 3, 4])

    def test_all_deactivated_series_remains_discoverable_and_restarts_at_one(self):
        row = self.add().json()["row"]
        self.client.post(f"{BASE}/{row['id']}/deactivate")
        data = self.read()
        self.assertEqual(data["rows"], [])
        self.assertEqual(data["series"], [{
            "incentive_type": 1, "score_type": "Delivery", "next_score": 1,
            "active_count": 0, "deactivated_count": 1,
        }])
        replacement = self.add(score_type="delivery", score=1).json()["row"]
        self.assertEqual(replacement["score"], 1)
        self.assertEqual(replacement["score_type"], "Delivery")
        self.assertNotEqual(replacement["id"], row["id"])
        self.assertEqual(len(self.read(include_deactivated=True)["rows"]), 2)

    def test_custom_positive_scores_are_saved_and_only_active_duplicates_are_rejected(self):
        self.assertEqual(self.add(score=7).json()["row"]["score"], 7)
        self.assertEqual(self.add(score=3).json()["row"]["score"], 3)
        self.assertEqual(self.read()["series"][0]["next_score"], 8)
        duplicate = self.add(score=3)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("already active", duplicate.json()["message"])
        self.assertEqual(len(self.read()["rows"]), 2)
        self.assertEqual(self.add().json()["row"]["score"], 8)

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

    def test_target_and_pr_are_required_floats_even_with_nullable_columns_or_defaults(self):
        for col in self.columns:
            if col["Field"] in ("target_increase", "pr_increase"):
                col.update(Null="YES", Default="0")
        for name in ("target_increase", "pr_increase"):
            for invalid in (None, "", "  ", "NaN", "Infinity", "1e999", False, [], {}):
                with self.subTest(field=name, value=invalid):
                    self.assertEqual(self.add(**{name: invalid}).status_code, 400)
            payload = {"city_group": "Group A", "incentive_type": 1, "score_type": "Delivery",
                       "target_increase": 0.25, "pr_increase": 1.5}
            del payload[name]
            self.assertEqual(self.client.post(BASE, json=payload).status_code, 400)
        row = self.add(target_increase=0, pr_increase="-0.125").json()["row"]
        self.assertEqual(row["target_increase"], 0.0)
        self.assertEqual(row["pr_increase"], -0.125)
        self.assertIsInstance(row["target_increase"], float)
        self.assertIsInstance(row["pr_increase"], float)

    def test_control_bucket_round_trips_null_or_three_floats_as_json(self):
        for value in (None, [0.125, 0.25, 0.625], [0, 1, -2.5]):
            with self.subTest(value=value):
                response = self.add(control_bucket=value)
                self.assertEqual(response.status_code, 200, response.text)
                saved = response.json()["row"]
                expected = None if value is None else [float(v) for v in value]
                self.assertEqual(saved["control_bucket"], expected)
                if expected is not None:
                    self.assertTrue(all(isinstance(v, float) for v in saved["control_bucket"]))
                read = next(row for row in self.read()["rows"] if row["id"] == saved["id"])
                self.assertEqual(read["control_bucket"], expected)
        with self.engine.connect() as conn:
            stored = conn.execute(text("SELECT control_bucket FROM incentive.incentive_decision_matrix WHERE id = 2")).scalar()
            self.assertEqual(stored, "[0.125,0.25,0.625]")

    def test_control_bucket_rejects_scalars_wrong_lengths_and_non_float_members(self):
        invalid = (0, 1.5, "", "[0.1,0.2,0.3]", {}, [], [0.1], [0.1, 0.2], [0, 1, 2, 3],
                   [0.1, None, 0.3], [True, 0.2, 0.3], ["0.1", 0.2, 0.3], [[0.1], 0.2, 0.3])
        for value in invalid:
            with self.subTest(value=value):
                response = self.add(control_bucket=value)
                self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.read()["rows"], [])

    def test_nullable_bucket_ignores_defaults_and_also_supports_json_in_text_columns(self):
        self.columns[7].update(Type="varchar(100)", Default="[0.1,0.2,0.3]")
        self.assertIsNone(self.add(control_bucket=None).json()["row"]["control_bucket"])
        self.assertEqual(self.add(control_bucket=[0.1, 0.2, 0.3]).json()["row"]["control_bucket"], [0.1, 0.2, 0.3])
        payload = {"city_group": "Group A", "incentive_type": 1, "score_type": "Quality",
                   "target_increase": 0.1, "pr_increase": 0.2}
        self.assertIsNone(self.client.post(BASE, json=payload).json()["row"]["control_bucket"])

    def test_incompatible_database_column_types_have_clear_errors(self):
        self.columns[7]["Type"] = "int"
        response = self.add(control_bucket=[0.1, 0.2, 0.3])
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON or text", response.json()["message"])
        self.columns[7].update(Type="json", Null="NO")
        response = self.add()
        self.assertEqual(response.status_code, 400)
        self.assertIn("allow NULL", response.json()["message"])
        self.columns[7]["Null"] = "YES"
        self.columns[5]["Type"] = "int"
        response = self.add()
        self.assertEqual(response.status_code, 400)
        self.assertIn("floating-point or decimal", response.json()["message"])

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

    def test_edit_endpoint_is_removed_and_cannot_change_existing_steps(self):
        row = self.add().json()["row"]
        response = self.client.put(f"{BASE}/{row['id']}", json={"target_increase": 9.5})
        self.assertIn(response.status_code, (404, 405))
        self.assertEqual(self.read()["rows"][0]["target_increase"], row["target_increase"])

    def test_deactivation_uses_the_same_lock_as_score_allocation(self):
        row = self.add().json()["row"]
        self.lock_result = 0
        self.assertEqual(self.client.post(f"{BASE}/{row['id']}/deactivate").status_code, 409)
        self.assertIsNone(self.read()["rows"][0]["deactivated_at"])

    def test_preset_labels_and_keys_save_canonical_database_values(self):
        for name, expected in [
            ("Performance", "performance"), ("PERFORMANCE", "performance"),
            ("weather", "weather"), ("Weather", "weather"),
            ("Order Level Increase", "order_level_increase"),
            ("order_level_increase", "order_level_increase"),
        ]:
            with self.subTest(name=name):
                response = self.add(score_type=name)
                self.assertEqual(response.status_code, 200, response.text)
                row = response.json()["row"]
                self.assertEqual(row["score_type"], expected)
                with self.engine.connect() as conn:
                    stored = conn.execute(text(
                        "SELECT score_type FROM incentive.incentive_decision_matrix WHERE id = :id"
                    ), {"id": row["id"]}).scalar()
                self.assertEqual(stored, expected)
        self.assertEqual({item["score_type"] for item in self.read()["series"]}, {
            "performance", "weather", "order_level_increase",
        })

    def test_legacy_preset_labels_share_scores_without_rewriting_history(self):
        legacy = self.add(score_type="order_level_increase", score=5).json()["row"]
        # Simulate a row saved by an older version; this only touches the test DB.
        with self.engine.begin() as conn:
            conn.execute(text(
                "UPDATE incentive.incentive_decision_matrix SET score_type = 'Order Level Increase' WHERE id = :id"
            ), {"id": legacy["id"]})
        self.assertEqual(self.add(score_type="order_level_increase").json()["row"]["score"], 6)
        self.assertEqual(self.add(score_type="Order Level Increase").json()["row"]["score"], 7)
        self.assertEqual(self.add(score_type="order_level_increase", score=5).status_code, 409)
        self.client.post(f"{BASE}/{legacy['id']}/deactivate")
        data = self.read(include_deactivated=True)
        self.assertEqual(data["series"], [{
            "incentive_type": 1, "score_type": "order_level_increase", "next_score": 8,
            "active_count": 2, "deactivated_count": 1,
        }])
        self.assertTrue(all(row["score_type"] == "order_level_increase" for row in data["rows"]))
        with self.engine.connect() as conn:
            stored = conn.execute(text(
                "SELECT score_type FROM incentive.incentive_decision_matrix WHERE id = :id"
            ), {"id": legacy["id"]}).scalar()
        self.assertEqual(stored, "Order Level Increase")

    def test_custom_score_names_are_not_reformatted(self):
        for name in ("Customer Experience", "Some_Custom_Name"):
            response = self.add(score_type=name)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["row"]["score_type"], name)

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

    def test_non_finite_float_and_bucket_members_are_rejected(self):
        for number in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(number=number):
                with self.assertRaises(matrix.MatrixError):
                    matrix._finite_float(number, "target_increase")
                with self.assertRaises(matrix.MatrixError):
                    matrix._control_bucket([number, 0.2, 0.3])

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
