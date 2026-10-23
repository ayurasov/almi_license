import pytest
from django.core.management import call_command
from django.db import connection

# Reverse dependency order: unapplying a module never leaves a dangling foreign key.
MODULES = ["audit", "packages", "activation", "licensing", "catalog"]


def domain_tables() -> set[str]:
    return {name for name in connection.introspection.table_names() if name.split("_")[0] in MODULES}


@pytest.mark.django_db(transaction=True)
def test_migrations_roll_back_to_zero_and_apply_again() -> None:
    applied = domain_tables()
    assert applied, "migrations create the domain tables"

    for module in MODULES:
        call_command("migrate", module, "zero", verbosity=0)
    assert domain_tables() == set()

    call_command("migrate", verbosity=0)
    assert domain_tables() == applied
