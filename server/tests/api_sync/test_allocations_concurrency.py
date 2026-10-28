"""Quotas of local servers are counted under the licence row lock (AGENTS.md, rule 6; section 5.2,
item 4 of document 2): parallel operators never hand out more seats than the licence has."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

from django.db import connection

from infra.clock import FrozenClock
from infra.errors import DomainError

OPERATORS = 8


def test_parallel_quotas_stay_within_the_limit(
    transactional_db: None, licensed: Any, clock: FrozenClock
) -> None:
    from apps.packages.domain import allocated_seats, create_server

    licensed.limit = 10
    licensed.save()
    barrier = Barrier(OPERATORS)

    def one(n: int) -> str:
        try:
            barrier.wait()
            create_server(
                licensed.customer_id,
                f"Сервер {n}",
                {str(licensed.id): 3},
                actor="user:op",
                now=clock.now(),
            )
            return "created"
        except DomainError:
            return "refused"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=OPERATORS) as pool:
        results = Counter(pool.map(one, range(OPERATORS)))

    assert results == {"created": 3, "refused": OPERATORS - 3}
    assert allocated_seats(licensed.id) == 9
