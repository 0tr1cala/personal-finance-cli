import csv
import hashlib
import json
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import Operation, Wallet, money
from .storage import WalletStore


class FinanceService:
    def __init__(self, store: WalletStore):
        self.store = store
        self.users: dict[str, str] = {}
        self.wallets: dict[str, Wallet] = {}
        self.current: str | None = None
        self.auth_path = getattr(store, "directory", Path("data")) / "users.json"
        if self.auth_path.exists():
            self.users = json.loads(self.auth_path.read_text(encoding="utf-8"))

    @staticmethod
    def _password_hash(password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
        return f"{salt}${digest}"

    def _save_users(self) -> None:
        self.auth_path.parent.mkdir(parents=True, exist_ok=True)
        self.auth_path.write_text(json.dumps(self.users, indent=2), encoding="utf-8")

    @staticmethod
    def _validate_credentials(username: str, password: str) -> None:
        if not username or not username.strip() or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in username):
            raise ValueError("Логин: используйте латинские буквы, цифры, _ или -.")
        if len(password) < 4:
            raise ValueError("Пароль должен содержать минимум 4 символа.")

    def register(self, username: str, password: str) -> Wallet:
        self._validate_credentials(username, password)
        if username in self.users or self.store.load(username) is not None:
            raise ValueError("Пользователь уже существует.")
        self.users[username] = self._password_hash(password)
        wallet = Wallet(username)
        self.wallets[username] = wallet
        self.store.save(wallet)
        self._save_users()
        self.current = username
        return wallet

    def login(self, username: str, password: str) -> Wallet:
        self._validate_credentials(username, password)
        if username in self.users:
            salt, expected = self.users[username].split("$", 1)
            if not secrets.compare_digest(self._password_hash(password, salt).split("$", 1)[1], expected):
                raise ValueError("Неверный логин или пароль.")
            wallet = self.wallets.get(username) or self.store.load(username)
            if wallet is None:
                wallet = Wallet(username)
            self.wallets[username] = wallet
        else:
            raise ValueError("Пользователь не найден. Сначала выполните register.")
        self.current = username
        return wallet

    def _wallet(self) -> Wallet:
        if not self.current:
            raise ValueError("Сначала войдите в аккаунт.")
        return self.wallets[self.current]

    def logout(self) -> None:
        if self.current:
            self.store.save(self._wallet())
            self.current = None

    def add_category(self, name: str, kind: str = "expense") -> None:
        wallet = self._wallet(); name = name.strip()
        if not name or kind not in ("income", "expense"):
            raise ValueError("Укажите название и тип категории income или expense.")
        wallet.categories[name] = kind
        self.store.save(wallet)

    def add_operation(self, kind: str, category: str, amount: object, when: str | None = None, note: str = "") -> list[str]:
        wallet = self._wallet()
        if category not in wallet.categories:
            raise ValueError(f"Категория «{category}» не найдена. Создайте её командой category.")
        if wallet.categories[category] != kind:
            raise ValueError("Тип операции не совпадает с типом категории.")
        operation = Operation.create(kind, category, amount, when, note)
        wallet.operations.append(operation)
        self.store.save(wallet)
        warnings = []
        if kind == "expense" and category in wallet.budgets:
            spent = self.total("expense", [category])
            budget = Decimal(wallet.budgets[category])
            if spent > budget:
                warnings.append(f"Превышен бюджет «{category}» на {spent - budget:.2f}.")
            elif spent >= budget * Decimal("0.8"):
                warnings.append(f"Использовано не менее 80% бюджета «{category}».")
        if wallet.balance < 0:
            warnings.append("Расходы превысили доходы: баланс отрицательный.")
        elif wallet.balance == 0 and wallet.operations:
            warnings.append("Баланс кошелька равен нулю.")
        return warnings

    def set_budget(self, category: str, amount: object) -> None:
        wallet = self._wallet()
        if wallet.categories.get(category) != "expense":
            raise ValueError(f"Расходная категория «{category}» не найдена.")
        wallet.budgets[category] = str(money(amount))
        self.store.save(wallet)

    def total(self, kind: str, categories: list[str] | None = None, since: str | None = None, until: str | None = None) -> Decimal:
        if kind not in ("income", "expense"):
            raise ValueError("Тип должен быть income или expense.")
        wallet = self._wallet()
        if categories:
            unknown = set(categories) - set(wallet.categories)
            if unknown:
                raise ValueError("Категории не найдены: " + ", ".join(sorted(unknown)))
        start = date.fromisoformat(since) if since else None
        end = date.fromisoformat(until) if until else None
        return sum((Decimal(op.amount) for op in wallet.operations if op.kind == kind
                    and (not categories or op.category in categories)
                    and (not start or date.fromisoformat(op.created_at) >= start)
                    and (not end or date.fromisoformat(op.created_at) <= end)), Decimal("0"))

    def summary(self) -> dict:
        wallet = self._wallet()
        totals = {kind: {} for kind in ("income", "expense")}
        for op in wallet.operations:
            totals[op.kind][op.category] = totals[op.kind].get(op.category, Decimal("0")) + Decimal(op.amount)
        budgets = {}
        for category, limit in wallet.budgets.items():
            spent = totals["expense"].get(category, Decimal("0"))
            budgets[category] = {"limit": Decimal(limit), "spent": spent, "remaining": Decimal(limit) - spent}
        return {"income": self.total("income"), "expense": self.total("expense"), "balance": wallet.balance,
                "by_category": totals, "budgets": budgets}

    def transfer(self, recipient: str, amount: object, note: str = "Перевод") -> None:
        sender_wallet = self._wallet()
        if recipient == sender_wallet.username:
            raise ValueError("Нельзя переводить деньги самому себе.")
        if recipient not in self.wallets:
            raise ValueError("Получатель должен войти в приложение в текущем сеансе.")
        value = money(amount)
        sender = Operation.create("expense", f"Перевод {recipient}", value, note=note)
        incoming = Operation.create("income", f"Перевод от {sender_wallet.username}", value, note=note)
        sender_wallet.operations.append(sender)
        self.wallets[recipient].operations.append(incoming)
        self.store.save(sender_wallet); self.store.save(self.wallets[recipient])

    def export(self, path: str, format_: str = "json") -> None:
        wallet = self._wallet()
        output = Path(path)
        if format_.lower() == "json":
            output.write_text(json.dumps(wallet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        elif format_.lower() == "csv":
            with output.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=["kind", "category", "amount", "created_at", "note"])
                writer.writeheader()
                writer.writerows(op.to_dict() for op in wallet.operations)
        else:
            raise ValueError("Формат экспорта: json или csv.")

    def import_json(self, path: str) -> None:
        wallet = self._wallet()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        imported = Wallet.from_dict(data)
        if imported.username != wallet.username:
            raise ValueError("Файл принадлежит другому пользователю.")
        for op in imported.operations:
            Operation.create(op.kind, op.category, op.amount, op.created_at, op.note)
        for category, amount in imported.budgets.items():
            money(amount)
            if imported.categories.get(category) != "expense":
                raise ValueError(f"Бюджет задан для неизвестной расходной категории: {category}.")
        self.wallets[wallet.username] = imported
        self.store.save(imported)

