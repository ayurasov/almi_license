from django.apps import AppConfig


class ActivationConfig(AppConfig):
    name = "apps.activation"
    label = "activation"

    def ready(self) -> None:
        # Automatic release runs hourly through the outbox queue (E12-02).
        from apps.activation.domain.autorelease import TASK_KIND, run_release_task
        from apps.outbox.domain import register_handler, register_schedule

        register_handler(TASK_KIND, run_release_task)
        register_schedule("activation.release_stale.hourly", "5 * * * *", TASK_KIND)
