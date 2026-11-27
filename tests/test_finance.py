import json
import tempfile
import unittest
from pathlib import Path

from finance_app.models import Operation, Wallet, money
from finance_app.service import FinanceService
from finance_app.storage import JsonWalletStore


class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = JsonWalletStore(self.temp.name)
        self.app = FinanceService(self.store)
        self.app.register("alice", "pass1234")

    def tearDown(self): self.temp.cleanup()

    def setup_expenses(self):
        self.app.add_category("Еда", "expense")
        self.app.add_category("Зарплата", "income")
        self.app.set_budget("Еда", 1000)

    def test_money_positive(self): self.assertEqual(money("2.345"), money("2.35"))
    def test_money_rejects_zero(self):
        with self.assertRaises(ValueError): money(0)
    def test_operation_rejects_bad_kind(self):
        with self.assertRaises(ValueError): Operation.create("other", "x", 1)
    def test_operation_rejects_empty_category(self):
        with self.assertRaises(ValueError): Operation.create("income", " ", 1)
    def test_operation_rejects_bad_date(self):
        with self.assertRaises(ValueError): Operation.create("income", "x", 1, "yesterday")
    def test_balance_tracks_operations(self):
        self.setup_expenses(); self.app.add_operation("income", "Зарплата", 2000); self.app.add_operation("expense", "Еда", 300)
        self.assertEqual(self.app.summary()["balance"], 1700)
    def test_category_required_for_operation(self):
        with self.assertRaisesRegex(ValueError, "не найдена"): self.app.add_operation("expense", "Еда", 1)
    def test_operation_kind_must_match_category(self):
        self.setup_expenses()
        with self.assertRaises(ValueError): self.app.add_operation("income", "Еда", 10)
    def test_category_type_cannot_be_redefined(self):
        self.setup_expenses()
        with self.assertRaisesRegex(ValueError, "другим типом"):
            self.app.add_category("Еда", "income")
    def test_budget_remaining(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 300)
        self.assertEqual(self.app.summary()["budgets"]["Еда"]["remaining"], 700)
    def test_budget_warning_at_eighty_percent(self):
        self.setup_expenses(); self.assertTrue(self.app.add_operation("expense", "Еда", 800))
    def test_budget_warning_when_exceeded(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 1000)
        self.assertIn("Превышен", self.app.add_operation("expense", "Еда", 1)[0])
    def test_category_totals(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 30); self.app.add_operation("expense", "Еда", 20)
        self.assertEqual(self.app.total("expense", ["Еда"]), 50)
    def test_unknown_filter_category(self):
        with self.assertRaisesRegex(ValueError, "не найдены"): self.app.total("expense", ["нет"])
    def test_date_filter(self):
        self.setup_expenses(); self.app.add_operation("income", "Зарплата", 40, "2025-01-01")
        self.assertEqual(self.app.total("income", since="2025-01-01", until="2025-01-01"), 40)
    def test_register_duplicate(self):
        with self.assertRaisesRegex(ValueError, "уже существует"): self.app.register("alice", "pass1234")
    def test_password_minimum(self):
        with self.assertRaises(ValueError): self.app.register("bob", "abc")
    def test_password_persists_and_wallet_loads(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 125)
        fresh = FinanceService(self.store); fresh.login("alice", "pass1234")
        self.assertEqual(fresh.summary()["expense"], 125)
    def test_bad_password_rejected(self):
        fresh = FinanceService(self.store)
        with self.assertRaisesRegex(ValueError, "Неверный"): fresh.login("alice", "wrongpass")
    def test_transfer_updates_both_wallets(self):
        self.app.register("bob", "pass1234"); self.app.login("alice", "pass1234")
        self.app.transfer("bob", 25)
        self.assertEqual(self.app.summary()["expense"], 25)
        self.app.login("bob", "pass1234"); self.assertEqual(self.app.summary()["income"], 25)
    def test_transfer_to_self_rejected(self):
        with self.assertRaises(ValueError): self.app.transfer("alice", 1)
    def test_transfer_to_user_without_session_login(self):
        self.app.register("bob", "pass1234")
        fresh = FinanceService(self.store)
        fresh.login("alice", "pass1234")
        fresh.transfer("bob", 25)
        self.assertEqual(self.store.load("bob").operations[0].kind, "income")
    def test_transfer_to_unknown_user_rejected(self):
        with self.assertRaisesRegex(ValueError, "не найден"):
            self.app.transfer("unknown", 10)
    def test_rename_category_updates_budget_and_history(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 50)
        self.app.rename_category("Еда", "Продукты")
        report = self.app.summary()
        self.assertEqual(report["budgets"]["Продукты"]["remaining"], 950)
        self.assertEqual(report["by_category"]["expense"]["Продукты"], 50)
    def test_rename_category_rejects_duplicate(self):
        self.setup_expenses()
        with self.assertRaisesRegex(ValueError, "уже существует"):
            self.app.rename_category("Еда", "Зарплата")
    def test_json_round_trip(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 80)
        path = Path(self.temp.name) / "backup.json"; self.app.export(str(path)); self.app.import_json(str(path))
        self.assertEqual(self.app.summary()["expense"], 80)
    def test_csv_export(self):
        self.setup_expenses(); self.app.add_operation("expense", "Еда", 5)
        path = Path(self.temp.name) / "backup.csv"; self.app.export(str(path), "csv")
        self.assertIn("Еда", path.read_text(encoding="utf-8-sig"))
    def test_csv_import(self):
        self.setup_expenses()
        path = Path(self.temp.name) / "transactions.csv"
        path.write_text("kind,category,amount,created_at,note\nexpense,Еда,75,2025-01-01,покупка\n", encoding="utf-8")
        self.app.import_file(str(path))
        self.assertEqual(self.app.summary()["expense"], 75)
    def test_csv_import_validates_columns(self):
        path = Path(self.temp.name) / "broken.csv"
        path.write_text("category,amount\nЕда,10\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "колонки"):
            self.app.import_csv(str(path))
    def test_wallet_serialization(self):
        wallet = Wallet("alice"); self.assertEqual(Wallet.from_dict(wallet.to_dict()).username, "alice")
    def test_invalid_budget_category(self):
        with self.assertRaises(ValueError): self.app.set_budget("missing", 10)
    def test_expense_exceeds_income_warning(self):
        self.app.add_category("Еда"); self.assertTrue(any("превысили доходы" in m for m in self.app.add_operation("expense", "Еда", 1)))


if __name__ == "__main__": unittest.main()

