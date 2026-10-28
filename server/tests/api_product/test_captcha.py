"""Question 45: captcha of the offline portal after 5 files from one address within an hour."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from infra.clock import FrozenClock, use_clock

pytestmark = pytest.mark.django_db
ANSWER = "ACE34"


@pytest.fixture(autouse=True)
def captcha_on(
    settings: Any, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FrozenClock]:
    import apps.api_product.domain.captcha as captcha

    settings.OFFLINE_CAPTCHA_AFTER = 2
    monkeypatch.setattr(captcha, "random_text", lambda alphabet, length: ANSWER)
    with use_clock(clock):
        yield clock


def upload(**fields: str) -> Any:
    file = SimpleUploadedFile("x.alk-req", b"{}", content_type="application/octet-stream")
    return Client().post("/api/v1/offline/requests", {"file": file, **fields})


def code(response: Any) -> str:
    value: str = response.json()["code"]
    return value


def new_captcha() -> dict[str, str]:
    response = Client().get("/api/v1/offline/captcha")
    assert response.status_code == 200
    body: dict[str, str] = response.json()
    return body


def test_captcha_after_the_free_files(captcha_on: FrozenClock) -> None:
    from apps.api_product.models import Captcha

    assert [code(upload()) for _ in range(2)] == ["invalid_request"] * 2  # the file is parsed
    refused = upload()
    assert (refused.status_code, code(refused)) == (400, "captcha_required")
    assert refused.json()["user_message"]["ru"] == "Введите символы с картинки."

    issued = new_captcha()
    assert issued["image"].startswith("data:image/png;base64,")
    assert ANSWER not in str(Captcha.objects.values_list("answer_hash", flat=True))
    wrong = upload(captcha_id=issued["captcha_id"], captcha_answer="XXXXX")
    assert code(wrong) == "captcha_required"
    # One attempt: the same captcha with the right answer is not accepted any more.
    assert code(upload(captcha_id=issued["captcha_id"], captcha_answer=ANSWER)) == (
        "captcha_required"
    )

    second = new_captcha()
    passed = upload(captcha_id=second["captcha_id"], captcha_answer=" ace34 ")
    assert code(passed) == "invalid_request"  # past the captcha, the file itself is refused
    assert not Captcha.objects.exists()


def test_expired_captcha_and_a_new_hour(captcha_on: FrozenClock) -> None:
    for _ in range(2):
        upload()
    issued = new_captcha()
    captcha_on.advance(timedelta(minutes=11))
    assert code(upload(captcha_id=issued["captcha_id"], captcha_answer=ANSWER)) == (
        "captcha_required"
    )
    captcha_on.advance(timedelta(hours=1))
    assert code(upload()) == "invalid_request"  # a new hour: free files again


def test_broken_captcha_id(captcha_on: FrozenClock) -> None:
    for _ in range(2):
        upload()
    assert code(upload(captcha_id="not-a-uuid", captcha_answer=ANSWER)) == "captcha_required"


def test_expired_captchas_are_purged(captcha_on: FrozenClock) -> None:
    from apps.api_product.domain.captcha import purge_captchas

    new_captcha()
    assert purge_captchas(captcha_on.now()) == 0
    assert purge_captchas(captcha_on.now() + timedelta(minutes=11)) == 1
