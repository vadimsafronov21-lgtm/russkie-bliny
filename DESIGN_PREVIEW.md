# Дизайн и отдельная демонстрация · 29.10.2026

В обзоре таблица занимает всю ширину. Один щелчок выбирает строку; кнопка «Подробности и график» или двойной щелчок открывают отдельное немодальное окно. В «Спросе» одновременно виден один тип анализа: продажи и прогноз, покрытие, доли блюд или запас по дням. Выбранная вкладка запоминается.

После сценарного аудита устранены наложения на небольшом экране, показатели привязаны к активному графику, заявка получила широкий состав и компактный итог. Поиск доступен в шапке, крупный режим и демонстрации — в профиле, замер — в пилоте. Редкие настройки раскрываются по запросу; ошибка открывает нужный блок. Расчётные формулы, ручные правки и защиты подтверждения сохранены.

Подсветка навигации меняется за 120–170 мс, подчёркивание вкладок скользит, заголовки мягко появляются. В профиле можно отключить «Плавные переходы». Постоянных циклов анимации нет. Кольцевая диаграмма масштабируется до 460 px, легенда расположена рядом, покрытие и график запаса используют доступную высоту.

## Запуск

Из корня репозитория с установленными зависимостями:

```powershell
.\.venv\Scripts\python.exe design_preview.py
```

Демонстрация использует отдельную сохраняемую базу `%LOCALAPPDATA%\RusskieBliny-DesignPreview\data.sqlite3`. При первом запуске создаются явно синтетические данные. Обычный запуск `app.py` использует `%LOCALAPPDATA%\RusskieBliny\data.sqlite3`; обе точки входа показывают текущий интерфейс.

Сборка отдельного EXE:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build.py --entry design_preview.py --name KronaDesignPreview
```

Результат — `dist/KronaDesignPreview.exe`. Обычный `build.py` собирает `dist/RusskieBliny.exe`. Готовые EXE и их локальные манифесты не хранятся в Git; ранее выданная сборка может отличаться от текущего кода.

## Проверка

Регрессии дизайна, сценарного аудита и переходов:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_calm_design.py tests/test_audit_fixes.py tests/test_motion.py tests/test_navigation.py tests/test_ui.py tests/test_interaction_ui.py
```

Для снимков используйте новую папку с синтетическими данными:

```powershell
.\.venv\Scripts\python.exe qa/verify_motion.py --data qa/motion-check-data --output qa/motion-check-screens
.\.venv\Scripts\python.exe qa/verify_audit_fixes.py --data qa/audit-check-data --output qa/audit-check-screens
.\.venv\Scripts\python.exe qa/verify_chart_hover.py --data qa/hover-check-data --output qa/hover-check-screens
```

Скрипты проверяют геометрию и снимают настоящий интерфейс Qt. Дополнительно доступен `qa/preview_calm_design.py --data ПАПКА --output ПАПКА`; `--source` задаёт каталог исходников для сравнения. Отчёты, снимки, записи, резервные копии и базы остаются локально. Проверка упакованного приложения: `dist/KronaDesignPreview.exe --data-dir qa/preview-exe-data --smoke qa/preview-exe-smoke`.
