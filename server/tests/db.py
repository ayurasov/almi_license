"""Helpers for checking database constraints and indexes in tests."""

from django.db import connection
from django.db.models import Model


def indexed_column_sets(model: type[Model]) -> list[tuple[str, ...]]:
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
    return [tuple(c["columns"]) for c in constraints.values() if c["index"] or c["unique"]]
