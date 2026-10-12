"""Независимый от интерфейса запуск: python -m blini.cli ..."""
import argparse
from pathlib import Path
from .config import Config
from .demo import generate_demo
from .data import load_csv_directory, validate_data
from .repository import save_dataset, load_dataset
from .service import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description="Учебный прогноз спроса и закупок ООО «Русские блины»")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Создать синтетические сценарии и CSV-шаблоны")
    demo.add_argument("--output", default="data/demo")
    demo.add_argument("--seed", type=int, default=42)
    validate = sub.add_parser("validate", help="Проверить папку CSV")
    validate.add_argument("--data", required=True)
    validate.add_argument("--as-of", required=True)
    run = sub.add_parser("run", help="Рассчитать CSV или сохранённый снимок SQLite")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--data")
    source.add_argument("--from-db")
    run.add_argument("--as-of")
    run.add_argument("--db", help="Сохранить успешно рассчитанный CSV-снимок в SQLite")
    run.add_argument("--config", default=None)
    run.add_argument("--output", default="reports/latest")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            generate_demo(args.output, args.seed)
            print(f"Учебные данные: {Path(args.output).resolve()}")
            return 0
        if args.command == "validate":
            result = validate_data(load_csv_directory(args.data), args.as_of)
            for line in result.errors + result.warnings:
                print(line)
            print(f"Ошибок: {len(result.errors)}; предупреждений: {len(result.warnings)}")
            return 2 if result.errors else 0
        if args.from_db:
            raw, as_of = load_dataset(args.from_db)
            if args.as_of and args.as_of != as_of:
                raise ValueError(f"Снимок SQLite относится к {as_of}; для другой даты импортируйте новый stock и deliveries")
        else:
            if not args.as_of:
                raise ValueError("Для CSV укажите --as-of — дату снимка stock")
            raw, as_of = load_csv_directory(args.data), args.as_of
        report = run_pipeline(raw, as_of, Config.load(args.config))
        if args.db:
            save_dataset(args.db, raw, as_of)
        report.export(args.output)
        print(report.recommendations[["ingredient", "unit", "order_quantity", "early_shortage", "status"]].to_string(index=False))
        print("\n" + "\n".join(report.warnings))
        print(f"\nРезультаты: {Path(args.output).resolve()}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Ошибка: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
