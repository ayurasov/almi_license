"""Writes tests/fixtures/lk-export-sample.xlsx: a synthetic LK export, 30 rows (E06-01).

Rows 1-16 are new licenses, 17 an update, 18 unchanged, 19-30 one error each. Keys are
made up and exist nowhere. Run from server/:
uv run python tests/fixtures/make_lk_export_sample.py
"""

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).with_name("lk-export-sample.xlsx")
HEADER = [
    "Серийный номер",
    "Код лицензии",
    "Артикул",
    "Количество",
    "Заказчик",
    "ИНН",
    "Дата выдачи",
]
INN = "7701234567"
OTHER_INN = "7712345678"
TERMS = ["01", "03", "06", "12", "24", "36", "99", "12"]


def key(n: int) -> str:
    return f"26{n:02}-TEST-ROWS-{n:04}"


def article(aa: str, ff: str) -> str:
    return f"{aa}-00-00-0-00-{ff}-00-00-00"


def row(n: int, *, aa: str = "01", ff: str = "12", **over: object) -> list[object]:
    art = str(over.get("article", article(aa, ff)))
    values: dict[str, object] = {
        "serial": f"26-{art}-001-{n:04}",
        "key": key(n),
        "article": art,
        "quantity": 10,
        "customer": "ООО «Пример»",
        "inn": INN,
        "issued": datetime(2026, 11, 1),
    } | over
    return [
        values[name]
        for name in ("serial", "key", "article", "quantity", "customer", "inn", "issued")
    ]


def rows() -> list[list[object]]:
    result = [row(n, aa="01" if n % 2 else "02", ff=TERMS[n % len(TERMS)]) for n in range(1, 16)]
    result.append(row(16, issued="15.11.2026"))  # a date typed as text
    result += [
        row(17, quantity=25),  # update: the license has 10 seats
        row(18),  # unchanged
        row(19, inn=INN),  # the key belongs to another customer (OTHER_INN in the database)
        row(20, key="1234-ABC"),
        row(21, key=key(1)),  # duplicate of row 1
        row(22, aa="77"),
        row(23, ff="05"),
        row(24, quantity=0),
        row(25, quantity="десять"),
        row(26, inn="12345"),
        row(27, issued="31.02.2026"),
        row(28, serial="XX"),
        row(29, serial=f"26-{article('02', '12')}-001-0029"),
        row(30, article="01-00"),
    ]
    return result


def main() -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Лицензии"
    sheet.append(HEADER)
    for values in rows():
        sheet.append(values)
    # Fixed metadata: the file is byte-stable across runs.
    book.properties.created = book.properties.modified = datetime(2026, 11, 1)
    book.save(OUT)


if __name__ == "__main__":
    main()
