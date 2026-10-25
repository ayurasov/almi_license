from django.apps import AppConfig


class PackagesConfig(AppConfig):
    name = "apps.packages"
    label = "packages"

    def ready(self) -> None:
        # A registered local server signs leases with its own key (E09-04); on the central
        # server the issuer key installed by the signing app is used and the factory stays idle.
        from apps.packages.domain.local import local_provider
        from apps.signing.domain import install_provider_factory

        install_provider_factory(local_provider)

        # A local server in the online exchange sends its usage report daily (E09-05).
        from apps.outbox.domain import register_handler, register_schedule
        from apps.packages.domain.local_usage import TASK_KIND, run_report_task

        register_handler(TASK_KIND, run_report_task)
        register_schedule("packages.usage_report.daily", "20 3 * * *", TASK_KIND)
