"""manage.py loadcatalog: the fixture of document 4 loads, is idempotent, profiles are versioned."""

import json
from pathlib import Path

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db
FIXTURE = Path(__file__).resolve().parents[1] / "apps" / "catalog" / "fixtures" / "catalog-v1.json"


def test_loads_products_editions_and_profiles() -> None:
    from apps.catalog.models import Edition, PolicyProfile, Product

    call_command("loadcatalog")
    call_command("loadcatalog")  # idempotent

    assert sorted(Product.objects.values_list("code", flat=True)) == [
        "alteroffice-desktop",
        "alteroffice-web",
        "alteros",
    ]
    professional = Edition.objects.get(product__code="alteroffice-desktop", code="professional")
    assert "macros" in professional.base_capabilities.values_list("code", flat=True)
    assert PolicyProfile.objects.filter(code="alteroffice-desktop.commercial").count() == 1
    assert Product.objects.get(code="alteros").default_profile_code == "alteros.commercial"


def test_changed_profile_gets_a_new_version(tmp_path: Path) -> None:
    from apps.catalog.models import PolicyProfile

    call_command("loadcatalog")
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    document["profiles"][0]["grace_days"] = 7
    changed = tmp_path / "catalog.json"
    changed.write_text(json.dumps(document), encoding="utf-8")

    call_command("loadcatalog", str(changed))

    versions = PolicyProfile.objects.filter(code="alteroffice-desktop.commercial").order_by(
        "version"
    )
    assert [(p.version, p.params["grace_days"]) for p in versions] == [(1, 14), (2, 7)]


def test_profiles_are_valid_policies() -> None:
    from apps.policy.domain import effective_policy

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for profile in document["profiles"]:
        params = {key: value for key, value in profile.items() if key != "code"}
        assert effective_policy(params, 1, "").version == 1
