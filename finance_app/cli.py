import shlex
from decimal import Decimal

from .service import FinanceService


HELP = """Команды:
  register <логин> <пароль>       создать пользователя и войти
  login <логин> <пароль>          войти в аккаунт
  logout                          сохранить кошелёк и выйти
  category <income|expense> <название>
  income <категория> <сумма> [YYYY-MM-DD] [заметка]
  expense <категория> <сумма> [YYYY-MM-DD] [заметка]
  budget <категория> <лимит>      создать или изменить бюджет
  report                          сводка доходов, расходов и бюджетов
  total <income|expense> [категория1,категория2] [с YYYY-MM-DD по YYYY-MM-DD]
  transfer <логин-получателя> <сумма> [заметка]
  export <путь> <json|csv>        импорт JSON: import <путь>
  help                            эта справка
  exit                            сохранить данные и завершить работу
Пример: category expense Еда; expense Еда 300
"""


def format_report(service: FinanceService) -> str:
    report = service.summary()
    lines = [f"Баланс: {report['balance']:.2f}", f"Доходы: {report['income']:.2f}", f"Расходы: {report['expense']:.2f}"]
    for kind, title in (("income", "Доходы по категориям"), ("expense", "Расходы по категориям")):
        lines.append(title + ":")
        lines.extend(f"  {name}: {amount:.2f}" for name, amount in sorted(report["by_category"][kind].items()))
        if not report["by_category"][kind]: lines.append("  нет данных")
    lines.append("Бюджеты:")
    lines.extend(f"  {name}: лимит {item['limit']:.2f}, потрачено {item['spent']:.2f}, осталось {item['remaining']:.2f}"
                 for name, item in sorted(report["budgets"].items()))
    if not report["budgets"]: lines.append("  бюджеты не заданы")
    return "\n".join(lines)


def run(service: FinanceService) -> None:
    print("Личные финансы. Введите help для списка команд.")
    while True:
        try:
            raw = input(f"[{service.current or 'гость'}] > ").strip()
            if not raw: continue
            parts = shlex.split(raw)
            command, args = parts[0].lower(), parts[1:]
            if command in ("exit", "quit"):
                service.logout(); print("Данные сохранены. До встречи!"); break
            if command == "help": print(HELP)
            elif command == "register": service.register(*args); print("Аккаунт создан, вход выполнен.")
            elif command == "login": service.login(*args); print("Вход выполнен.")
            elif command == "logout": service.logout(); print("Вы вышли из аккаунта.")
            elif command == "category": service.add_category(args[1], args[0]); print("Категория сохранена.")
            elif command in ("income", "expense"):
                warnings = service.add_operation(command, args[0], args[1], args[2] if len(args) > 2 else None,
                                                 " ".join(args[3:]) if len(args) > 3 else "")
                print("Операция добавлена.")
                for warning in warnings: print("Внимание:", warning)
            elif command == "budget": service.set_budget(args[0], args[1]); print("Бюджет сохранён.")
            elif command == "report": print(format_report(service))
            elif command == "total":
                cats = args[1].split(",") if len(args) > 1 else None
                since = args[3] if len(args) > 3 else None
                until = args[5] if len(args) > 5 else None
                print(f"Итого: {service.total(args[0], cats, since, until):.2f}")
            elif command == "transfer": service.transfer(args[0], args[1], " ".join(args[2:])); print("Перевод выполнен.")
            elif command == "export": service.export(args[0], args[1]); print("Экспорт завершён.")
            elif command == "import": service.import_json(args[0]); print("Импорт завершён.")
            else: print("Неизвестная команда. Введите help.")
        except (ValueError, IndexError, OSError, KeyError) as error:
            print(f"Ошибка: {error}")
        except EOFError:
            service.logout(); print("\nДанные сохранены."); break

