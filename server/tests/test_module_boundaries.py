"""AGENTS.md rule 3 at the database level: a module does not reference another module's
tables, except licensing -> catalog and activation -> licensing (docs/decisions.md, I1-03)."""

from django.apps import apps
from django.db.models import Model

# iam -> auth: console users are django.contrib.auth users, owned by iam (decision E07-02).
ALLOWED = {("licensing", "catalog"), ("activation", "licensing"), ("iam", "auth")}
DOMAIN_APPS = {config.label for config in apps.get_app_configs() if config.name.startswith("apps.")}


def test_foreign_keys_cross_modules_only_where_allowed() -> None:
    crossing = set()
    for model in apps.get_models():
        source = model._meta.app_label
        if source not in DOMAIN_APPS:
            continue
        for field in model._meta.get_fields():
            related = field.related_model
            if not (field.is_relation and field.concrete and isinstance(related, type)):
                continue
            if issubclass(related, Model):
                target = related._meta.app_label
                if target != source:
                    crossing.add((source, target, f"{model.__name__}.{field.name}"))
    assert {(s, t) for s, t, _ in crossing} <= ALLOWED, sorted(crossing)


def test_every_domain_table_has_uuid_primary_key() -> None:
    for model in apps.get_models():
        if model._meta.app_label in DOMAIN_APPS:
            assert model._meta.pk.get_internal_type() == "UUIDField", model.__name__
