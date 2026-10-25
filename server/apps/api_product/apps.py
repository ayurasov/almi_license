from django.apps import AppConfig

PURGE_KIND = "api_product.idempotency_purge"


class ApiProductConfig(AppConfig):
    name = "apps.api_product"
    label = "api_product"

    def ready(self) -> None:
        # Stored first responses older than 24 h are removed hourly (E05-02, E12-01).
        from apps.api_product.domain.idempotency import run_purge_task
        from apps.outbox.domain import register_handler, register_schedule

        register_handler(PURGE_KIND, run_purge_task)
        register_schedule("api_product.idempotency_purge.hourly", "35 * * * *", PURGE_KIND)
