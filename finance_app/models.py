from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal


def money(value: object) -> Decimal:
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError("Сумма должна быть числом.") from None
    if not result.is_finite() or result <= 0:
        raise ValueError("Сумма должна быть больше нуля.")
    return result


@dataclass
class Operation:
    kind: Literal["income", "expense"]
    category: str
    amount: str
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    note: str = ""

    @classmethod
    def create(cls, kind: str, category: str, amount: object, created_at: str | None = None, note: str = "") -> "Operation":
        if kind not in ("income", "expense"):
            raise ValueError("Тип операции должен быть income или expense.")
        category = category.strip()
        if not category:
            raise ValueError("Название категории не может быть пустым.")
        when = date.fromisoformat(created_at).isoformat() if created_at else date.today().isoformat()
        return cls(kind, category, str(money(amount)), when, note.strip())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Wallet:
    username: str
    categories: dict[str, str] = field(default_factory=dict)
    budgets: dict[str, str] = field(default_factory=dict)
    operations: list[Operation] = field(default_factory=list)

    @property
    def balance(self) -> Decimal:
        return sum((Decimal(op.amount) * (1 if op.kind == "income" else -1) for op in self.operations), Decimal("0"))

    def to_dict(self) -> dict:
        return {"username": self.username, "categories": self.categories, "budgets": self.budgets,
                "operations": [op.to_dict() for op in self.operations]}

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(data["username"], dict(data.get("categories", {})), dict(data.get("budgets", {})),
                   [Operation(**item) for item in data.get("operations", [])])
