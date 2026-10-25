from django.apps import AppConfig


class ActivationConfig(AppConfig):
    name = "apps.activation"
    label = "activation"

    def ready(self) -> None:
        # Automatic release runs hourly through the outbox queue (E12-02).
        # States of licences are recalculated hourly for the console and statistics (E12-03).
        from apps.activation.domain import autorelease, states
        from apps.outbox.domain import register_handler, register_schedule

        register_handler(autorelease.TASK_KIND, autorelease.run_release_task)
        register_schedule("activation.release_stale.hourly", "5 * * * *", autorelease.TASK_KIND)
        register_handler(states.TASK_KIND, states.run_recompute_task)
        register_schedule("licensing.recompute_states.hourly", "15 * * * *", states.TASK_KIND)
