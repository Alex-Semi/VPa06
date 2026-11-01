# VPa06 — Генератор PDF-счетов (invoice → PDF)

Консольный скрипт на Python: читает данные из CSV/JSON, подставляет их в HTML-шаблон
и генерирует PDF с помощью **WeasyPrint** (с поддержкой кириллицы — DejaVu Sans / Roboto).
Работает на **Windows** и **macOS** (и на Linux).

## Возможности

- Сканирование директории `data/` — все доступные `.csv` и `.json` файлы.
  - CSV парсится через **pandas** (fallback на стандартный модуль `csv`);
  - JSON парсится стандартной библиотекой **json**.
- Сканирование директории `templates/` — все HTML-шаблоны (`.html`, `.htm`).
- Нумерованное меню выбора: файл данных → шаблон → конкретный счёт (по invoice id).
- Генерация PDF в директорию `output/` (`invoice_<ID>.pdf`).
- Автооткрытие готового PDF системной программой:
  Windows — `os.startfile()`, macOS — `open`, Linux — `xdg-open`.
- Шаблон поддерживает подстановку `{{ поле }}` или `{поле}` (например, `{{ invoice_id }}`).

## Структура проекта

```
VPa06/
├── generate_invoice_pdf.py   # основной скрипт
├── requirements.txt          # зависимости
├── data/                     # CSV/JSON с данными счетов
│   ├── invoices.csv
│   └── invoices.json
├── templates/                # HTML-шаблоны
│   └── invoice.html
└── output/                   # сюда сохраняются PDF (в .gitignore)
```

## Установка

```bash
git clone https://github.com/Alex-Csl/VPa06.git
cd VPa06
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

Требования Python: pandas, WeasyPrint. На Linux для WeasyPrint нужны системные
библиотеки Pango/GTK (`sudo apt install libpango-1.0-0 libpangocairo-1.0-0` и т.п.);
на Windows и macOS достаточно `pip install`.

Шрифты **DejaVu Sans** / **Roboto** подключаются скриптом автоматически;
для надёжной кириллицы установите один из них в систему (обычно уже есть).

## Запуск

```bash
python generate_invoice_pdf.py
```

Скрипт выведет список доступных файлов данных и шаблонов, затем попросит:

1. выбрать файл с данными (номер из списка);
2. выбрать HTML-шаблон;
3. выбрать конкретный счёт (invoice id) — по нему сгенерируется PDF в `output/`
   и автоматически откроется в системной программе просмотра.

## Данные

Файл может содержать несколько счетов (CSV — строки, JSON — массив объектов или
объект со списком). Скрипт распознаёт ключи `invoice_id`, `InvoiceID`,
`invoice_number`, `номер_счета` и т.п. Остальные поля доступны в шаблоне по именам колонок.
