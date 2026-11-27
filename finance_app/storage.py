import json
from pathlib import Path
from typing import Protocol

from .models import Wallet


class WalletStore(Protocol):
    def load(self, username: str) -> Wallet | None: ...
    def save(self, wallet: Wallet) -> None: ...


class JsonWalletStore:
    """Stores each user's wallet as a separate JSON document."""
    def __init__(self, directory: str | Path = "data"):
        self.directory = Path(directory)

    def _path(self, username: str) -> Path:
        safe = "".join(c for c in username if c.isalnum() or c in "-_" )
        if not safe or safe != username:
            raise ValueError("Некорректный логин для имени файла.")
        return self.directory / f"{safe}.json"

    def load(self, username: str) -> Wallet | None:
        path = self._path(username)
        if not path.exists():
            return None
        return Wallet.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, wallet: Wallet) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(wallet.username)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(wallet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

