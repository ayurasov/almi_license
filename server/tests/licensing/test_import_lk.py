"""Preview of an LK XLSX export (E06-01, E06-02; section 14.1 of document 2, section 8 of doc. 4).

Outside the apps package: the test prepares catalog and licensing rows for the cases.
"""

import io
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from apps.licensing.domain import ImportFileError, key_hash, parse_lk_export
from infra.clock import FrozenClock

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "lk-export-sample.xlsx"
INN = "7701234567"
OTHER_INN = "7712345678"

pytestmark = pytest.mark.django_db


def sample_key(n: int) -> str:
    return f"26{n:02}-TEST-ROWS-{n:04}"


@pytest.fixture
def catalog(clock: FrozenClock) -> dict[str, Any]:
    from apps.catalog.models import Edition, Metric, Product
    from apps.licensing.models import ArticleMapping

    device = Metric.objects.create(code="device")
    instance = Metric.objects.create(code="server_instance")
    desktop = Product.objects.create(
        code="alteroffice-desktop",
        default_metric=device,
        subject_type="device",
        created_at=clock.now(),
    )
    web = Product.objects.create(
        code="alteroffice-web",
        default_metric=instance,
        subject_type="server_instance",
        created_at=clock.now(),
    )
    standard = Edition.objects.create(product=desktop, code="standard")
    enterprise = Edition.objects.create(product=web, code="enterprise")
    ArticleMapping.objects.create(aa="01", product=desktop, edition=standard, metric=device)
    ArticleMapping.objects.create(aa="02", product=web, edition=enterprise, metric=instance)
    return {"desktop": desktop, "standard": standard, "device": device}


def existing_license(
    catalog: dict[str, Any], clock: FrozenClock, n: int, inn: str, limit: int
) -> None:
    from apps.licensing.domain import key_mask
    from apps.licensing.models import Customer, License, LicenseKey

    customer, _ = Customer.objects.get_or_create(
        inn=inn, defaults={"name": f"Заказчик {inn}", "created_at": clock.now()}
    )
    license_ = License.objects.create(
        customer=customer,
        product=catalog["desktop"],
        edition=catalog["standard"],
        metric=catalog["device"],
        type="subscription",
        limit=limit,
        valid_from=datetime(2026, 10, 31, 21, tzinfo=UTC),  # 01.11.2026 00:00 MSK
        valid_until=datetime(2027, 10, 31, 20, 59, 59, tzinfo=UTC),  # 31.10.2027 23:59:59 MSK
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    LicenseKey.objects.create(
        license=license_,
        key_hash=key_hash(sample_key(n)),
        key_mask=key_mask(sample_key(n)),
        format="v1",
    )


@pytest.fixture
def preview(catalog: dict[str, Any], clock: FrozenClock) -> Any:
    existing_license(catalog, clock, 17, INN, limit=10)
    existing_license(catalog, clock, 18, INN, limit=10)
    existing_license(catalog, clock, 19, OTHER_INN, limit=10)
    return parse_lk_export(SAMPLE.read_bytes(), filename="lk-export-sample.xlsx", now=clock.now())


EXPECTED_ERRORS = {
    19: "Ключ принадлежит другому заказчику",
    20: "Неверный формат кода лицензии",
    21: "Код лицензии повторяется в файле: строка 2",
    22: "Артикул не сопоставлен: 77",
    23: "Неизвестный срок FF: 05",
    24: "Количество должно быть целым числом больше нуля",
    25: "Количество должно быть целым числом больше нуля",
    26: "Неверный ИНН",
    27: "Неверная дата выдачи",
    28: "Неверный серийный номер",
    29: "Серийный номер не соответствует артикулу",
    30: "Неверный артикул",
}


def test_statuses_and_reasons_of_the_sample(preview: Any) -> None:
    by_number = {row.row - 1: row for row in preview.rows}  # data row n is spreadsheet row n + 1

    assert len(preview.rows) == 30
    assert [by_number[n].status for n in range(1, 17)] == ["new"] * 16
    assert (by_number[17].status, by_number[17].errors) == ("update", [])
    assert (by_number[18].status, by_number[18].errors) == ("skip", [])
    for n, reason in EXPECTED_ERRORS.items():
        assert (n, by_number[n].status, by_number[n].errors) == (n, "error", [reason])
    assert preview.summary == {"new": 16, "update": 1, "skip": 1, "error": 12}


def test_recognised_fields(preview: Any) -> None:
    first, sixth, sixteenth = (preview.rows[n - 1].fields for n in (1, 6, 16))

    assert first == {
        "serial": "26-01-00-00-0-00-03-00-00-00-001-0001",
        "key_mask": "2601-****-****-0001",
        "article": "01-00-00-0-00-03-00-00-00",
        "aa": "01",
        "ff": "03",
        "product": "alteroffice-desktop",
        "edition": "standard",
        "metric": "device",
        "type": "subscription",
        "valid_from": "2026-10-31T21:00:00Z",
        "valid_until": "2027-01-31T20:59:59Z",
        "limit": 10,
        "inn": INN,
        "customer": "ООО «Пример»",
    }
    assert sixth["type"] == "perpetual" and sixth["valid_until"] is None
    assert sixteenth["valid_from"] == "2026-11-14T21:00:00Z"  # "15.11.2026" typed as text


def test_full_key_never_reaches_the_preview(preview: Any) -> None:
    from apps.licensing.models import ImportSession

    session = ImportSession.objects.get(id=preview.session_id)
    stored = str(session.rows) + str(session.summary)
    for n in range(1, 31):
        assert sample_key(n) not in stored
        assert sample_key(n) not in repr(preview)


def test_session_is_a_draft_for_24_hours(preview: Any, clock: FrozenClock) -> None:
    from apps.licensing.models import ImportSession, License

    session = ImportSession.objects.get(id=preview.session_id)

    assert session.status == "draft" and session.filename == "lk-export-sample.xlsx"
    assert session.expires_at == clock.now() + timedelta(hours=24)
    assert len(session.rows) == 30
    assert License.objects.count() == 3  # nothing written to licenses


def workbook(header: list[str], *rows: Sequence[object]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(header)
    for values in rows:
        sheet.append(list(values))
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_empty_file(catalog: dict[str, Any], clock: FrozenClock) -> None:
    with pytest.raises(ImportFileError, match="В файле нет данных"):
        parse_lk_export(workbook([]), filename="empty.xlsx", now=clock.now())


def test_header_without_rows(catalog: dict[str, Any], clock: FrozenClock) -> None:
    header = ["Серийный номер", "Код лицензии", "Артикул", "Количество", "ИНН", "Дата выдачи"]
    with pytest.raises(ImportFileError, match="В файле нет данных"):
        parse_lk_export(workbook(header), filename="header.xlsx", now=clock.now())


def test_missing_key_column(catalog: dict[str, Any], clock: FrozenClock) -> None:
    from apps.licensing.models import ImportSession

    header = ["Серийный номер", "Артикул", "Количество", "ИНН", "Дата выдачи"]
    with pytest.raises(ImportFileError, match="Нет обязательной колонки: Код лицензии"):
        parse_lk_export(workbook(header, ["x"] * 5), filename="no-key.xlsx", now=clock.now())
    assert ImportSession.objects.count() == 0


def test_headers_ignore_case_spaces_and_synonyms(
    catalog: dict[str, Any], clock: FrozenClock
) -> None:
    header = [
        "  СЕРИЙНЫЙ  НОМЕР",
        "код лицензии",
        "Артикул ",
        "TotalLicenses",
        "инн",
        "Дата  выдачи",
    ]
    article = "01-00-00-0-00-12-00-00-00"
    preview = parse_lk_export(
        workbook(
            header,
            [f"26-{article}-001-0001", sample_key(1), article, 3, INN, datetime(2026, 11, 1)],
        ),
        filename="x.xlsx",
        now=clock.now(),
    )
    assert preview.rows[0].status == "new" and preview.rows[0].fields["customer"] == ""


def test_not_an_xlsx(clock: FrozenClock) -> None:
    with pytest.raises(ImportFileError, match="не является книгой XLSX"):
        parse_lk_export(b"name;key\n", filename="x.csv", now=clock.now())


def test_size_limit(clock: FrozenClock) -> None:
    with pytest.raises(ImportFileError, match="20 МБ"):
        parse_lk_export(b"0" * (20 * 1024 * 1024 + 1), filename="big.xlsx", now=clock.now())


def test_row_limit(
    catalog: dict[str, Any], clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.licensing.domain import import_lk

    monkeypatch.setattr(import_lk, "MAX_ROWS", 2)
    header = ["Серийный номер", "Код лицензии", "Артикул", "Количество", "ИНН", "Дата выдачи"]
    with pytest.raises(ImportFileError, match="больше 2 строк"):
        parse_lk_export(workbook(header, *[["x"] * 6] * 3), filename="x.xlsx", now=clock.now())
