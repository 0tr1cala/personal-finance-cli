import argparse

from .cli import run
from .service import FinanceService
from .storage import JsonWalletStore


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI-приложение для учёта личных финансов")
    parser.add_argument("--data-dir", default="data", help="каталог с файлами кошельков и учётных записей")
    args = parser.parse_args()
    run(FinanceService(JsonWalletStore(args.data_dir)))


if __name__ == "__main__":
    main()

