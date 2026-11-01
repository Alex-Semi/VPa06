#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор PDF-счетов из CSV/JSON данных по HTML-шаблону.

Что делает скрипт:
  1. Сканирует директорию ./data на наличие файлов .csv и .json.
  2. Сканирует директорию ./templates на наличие HTML-шаблонов (.html / .htm).
  3. Показывает нумерованное меню, позволяет выбрать файл данных и шаблон (input).
  4. Выводит список доступных счетов (по полю invoice_id / InvoiceID / invoice id и т.п.).
  5. Подставляет данные выбранного счета в шаблон и генерирует PDF через WeasyPrint.
  6. Сохраняет PDF в ./output и открывает его системной программой (Windows / macOS / Linux).

Поддержка кириллицы обеспечивается шрифтом DejaVu Sans (или Roboto),
который подключается прямо в CSS сгенерированного документа.

Требования:
    pip install weasyprint pandas

Работает на Windows и macOS (и Linux).
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Пути (относительно расположения самого скрипта)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"

# Ключи, в которых может лежать номер счета (приводятся к нижнему регистру)
INVOICE_ID_KEYS = ("invoice_id", "invoiceid", "invoice id", "invoicenumber",
                   "invoice_number", "номер_счета", "счет")


# ---------------------------------------------------------------------------
# Чтение данных
# ---------------------------------------------------------------------------
def find_data_files() -> list[Path]:
    """Возвращает все .csv и .json файлы в директории данных."""
    if not DATA_DIR.is_dir():
        return []
    files = [p for p in DATA_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in (".csv", ".json")]
    return sorted(files, key=lambda p: p.name.lower())


def find_template_files() -> list[Path]:
    """Возвращает все HTML-шаблоны в директории шаблонов."""
    if not TEMPLATES_DIR.is_dir():
        return []
    files = [p for p in TEMPLATES_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in (".html", ".htm")]
    return sorted(files, key=lambda p: p.name.lower())


def load_records(path: Path) -> list[dict]:
    """
    Читает CSV или JSON и возвращает список записей (dict).

    CSV  — через pandas (fallback на стандартный csv).
    JSON — стандартной библиотекой json; поддерживается как список объектов,
           так и объект со списком внутри (например {"invoices": [...]}).
    """
    suffix = path.suffix.lower()

    if suffix == ".csv":
        try:
            import pandas as pd
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            return df.to_dict(orient="records")
        except ImportError:
            import csv
            with open(path, newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))

    if suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            # Ищем первый список словарей внутри объекта
            for value in data.values():
                if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                    return value
            return [data]  # один запись-объект
        raise ValueError(f"Неожиданный формат JSON: {path}")

    raise ValueError(f"Неподдерживаемый формат файла: {path}")


def get_invoice_id(record: dict) -> str | None:
    """Достаёт номер счета из записи по одному из известных ключей."""
    lowered = {str(k).strip().lower().replace("-", "_"): v for k, v in record.items()}
    for key in INVOICE_ID_KEYS:
        norm = key.strip().lower().replace("-", "_").replace(" ", "_")
        if norm in lowered and lowered[norm] not in (None, ""):
            return str(lowered[norm])
    # Если ничего не нашли — попробуем любое поле, содержащее "invoice"
    for k, v in lowered.items():
        if "invoice" in k and v not in (None, ""):
            return str(v)
    return None


# ---------------------------------------------------------------------------
# Меню консоли
# ---------------------------------------------------------------------------
def print_menu(title: str, items: list[str]) -> None:
    print()
    print("=" * 60)
    print(title)
    print("-" * 60)
    for i, item in enumerate(items, start=1):
        print(f"  {i:>3}. {item}")
    print("=" * 60)


def choose_item(title: str, items: list[str], allow_empty: bool = False) -> int | None:
    """Нумерованное меню + ввод пользователя. Возвращает индекс (0-based)."""
    print_menu(title, items)
    while True:
        raw = input(f"Выберите вариант (1-{len(items)}"
                    + (", 0 — пропустить" if allow_empty else "") + "): ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(items):
                return idx - 1
            if idx == 0 and allow_empty:
                return None
        print("  !! Неверный ввод, попробуйте ещё раз.")


# ---------------------------------------------------------------------------
# Рендеринг шаблона
# ---------------------------------------------------------------------------
def render_template(template_text: str, record: dict) -> str:
    """
    Подставляет значения из записи в шаблон.

    Поддерживаются два синтаксиса:
      1. Jinja-like: {{ invoice_id }}, {{ total }} … (реализовано простым
         заменителем, без зависимости от jinja2).
      2. str.format: {invoice_id} — используется только если в шаблоне нет {{ }}.
    """
    def _fmt_value(v):
        if isinstance(v, float):
            # красиво печатаем числа: 1234.5 -> 1 234.50
            return f"{v:,.2f}".replace(",", " ")
        return "" if v is None else str(v)

    flat = {k: _fmt_value(v) for k, v in record.items()}

    # 1) Замены вида {{ key }}
    def repl(m: re.Match) -> str:
        key = m.group(1).strip()
        return flat.get(key, m.group(0))

    rendered = re.sub(r"\{\{\s*([\w\.\-]+)\s*\}\}", repl, template_text)

    # 2) Если остались одиночные {key} — пробуем format_map (безопасно:
    #    пропущенные ключи остаются как есть через default-dict)
    class SilentDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    if "{" in rendered:
        try:
            rendered = rendered.replace("{{", "{").replace("}}", "}")
            rendered = rendered.format_map(SilentDict(flat))
        except (ValueError, KeyError):
            pass  # сложный шаблон — оставляем как есть

    return rendered


def ensure_cyrillic_css(html: str) -> str:
    """
    Гарантирует, что в документе будет стиль с кириллическим шрифтом
    (DejaVu Sans / Roboto), даже если сам шаблон о нём забыл.
    """
    css = (
        "@font-face{font-family:'DejaVu Sans';"
        "src:local('DejaVu Sans'),local('DejaVuSans');"
        "font-weight:normal;font-style:normal}"
        "@font-face{font-family:'Roboto';"
        "src:local('Roboto'),local('Roboto-Regular');}"
        "*{font-family:'DejaVu Sans','Roboto',sans-serif}"
        "body{font-family:'DejaVu Sans','Roboto',sans-serif}"
    )
    style_tag = f"<style>{css}</style>"
    if "</head>" in html.lower():
        idx = html.lower().index("</head>")
        return html[:idx] + style_tag + html[idx:]
    if "<body" in html.lower():
        idx = html.lower().index("<body")
        end = html.find(">", idx) + 1
        return html[:end] + style_tag + html[end:]
    return style_tag + html


# ---------------------------------------------------------------------------
# Открытие PDF в системной программе
# ---------------------------------------------------------------------------
def open_pdf(path: Path) -> None:
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":  # macOS
            subprocess.run(["open", str(path)], check=False)
        else:  # Linux и прочие
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:  # noqa: BLE001
        print(f"  ! Не удалось автоматически открыть PDF: {e}")
        print(f"  ! Откройте его вручную: {path}")


# ---------------------------------------------------------------------------
# Основная программа
# ---------------------------------------------------------------------------
def main() -> int:
    print("\n" + "#" * 60)
    print("#   Генератор PDF-счетов (CSV/JSON + HTML-шаблон + WeasyPrint)")
    print("#" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data_files = find_data_files()
    template_files = find_template_files()

    print("\nДоступные файлы данных ({}):".format(DATA_DIR))
    if data_files:
        for p in data_files:
            print(f"   • {p.name}")
    else:
        print("   (нет файлов)")

    print("\nДоступные HTML-шаблоны ({}):".format(TEMPLATES_DIR))
    if template_files:
        for p in template_files:
            print(f"   • {p.name}")
    else:
        print("   (нет файлов)")

    if not data_files:
        print("\nОшибка: в директории ./data нет ни одного .csv/.json файла.")
        return 1
    if not template_files:
        print("\nОшибка: в директории ./templates нет ни одного HTML-шаблона.")
        return 1

    # Выбор файла данных
    idx_data = choose_item("Файлы данных", [p.name for p in data_files])
    data_path = data_files[idx_data]

    try:
        records = load_records(data_path)
    except Exception as e:  # noqa: BLE001
        print(f"\nОшибка чтения файла {data_path.name}: {e}")
        return 1

    if not records:
        print(f"\nВ файле {data_path.name} нет записей.")
        return 1

    # Список счетов
    invoices: list[tuple[str, dict]] = []
    for rec in records:
        inv_id = get_invoice_id(rec)
        if inv_id is not None:
            invoices.append((inv_id, rec))

    if not invoices:
        print("\nВ выбранном файле не найдено поле номера счета "
              "(invoice_id / InvoiceID / ...).")
        return 1

    # Убираем дубликаты id для отображения
    seen, unique_invoices = set(), []
    for inv_id, rec in invoices:
        if inv_id not in seen:
            seen.add(inv_id)
            unique_invoices.append((inv_id, rec))

    labels = []
    for inv_id, rec in unique_invoices:
        extra_bits = []
        for name_key in ("customer", "client", "name", "organization",
                         "покупатель", "клиент", "название"):
            for k in rec:
                if k.strip().lower() == name_key and rec[k]:
                    extra_bits.append(str(rec[k]))
                    break
            if extra_bits:
                break
        label = f"Invoice {inv_id}"
        if extra_bits:
            label += f" — {extra_bits[0]}"
        labels.append(label)

    idx_inv = choose_item("Доступные счета (invoice id)", labels)
    inv_id, record = unique_invoices[idx_inv]

    # Выбор шаблона
    idx_tpl = choose_item("HTML-шаблоны", [p.name for p in template_files])
    tpl_path = template_files[idx_tpl]

    template_text = tpl_path.read_text(encoding="utf-8")
    html = render_template(template_text, record)
    html = ensure_cyrillic_css(html)

    # Генерация PDF
    try:
        from weasyprint import HTML
    except ImportError:
        print("\nОшибка: библиотека WeasyPrint не установлена.")
        print("Установите её командой:  pip install weasyprint")
        return 1

    safe_id = re.sub(r"[^\w\-]+", "_", inv_id)
    pdf_path = OUTPUT_DIR / f"invoice_{safe_id}.pdf"

    print(f"\nГенерация PDF: {pdf_path} ...")
    try:
        HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(pdf_path))
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка генерации PDF: {e}")
        return 1

    print(f"Готово! Файл сохранён: {pdf_path}")

    # Автооткрытие
    open_pdf(pdf_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(130)
