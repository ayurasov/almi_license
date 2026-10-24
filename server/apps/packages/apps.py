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
