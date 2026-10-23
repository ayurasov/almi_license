"""Request and response shapes of Product API v1 (contracts/openapi-product-api-v1.yaml)."""

from typing import Any

from rest_framework import serializers


class ProductSerializer(serializers.Serializer[dict[str, Any]]):
    code = serializers.RegexField(r"^[a-z0-9-]{2,64}$")
    version = serializers.CharField(max_length=64)
    build = serializers.CharField(max_length=64, required=False)
    edition = serializers.CharField(max_length=64, required=False)


class OsInfoSerializer(serializers.Serializer[dict[str, Any]]):
    family = serializers.ChoiceField(["windows", "linux", "macos", "other"])
    name = serializers.CharField(max_length=128)
    version = serializers.CharField(max_length=64)
    arch = serializers.ChoiceField(["x86_64", "aarch64", "x86", "other"])


class InstanceSerializer(serializers.Serializer[dict[str, Any]]):
    instance_id = serializers.UUIDField()
    subject_type = serializers.ChoiceField(["device", "server_instance", "os_node"])
    name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    os = OsInfoSerializer()


class FingerprintSerializer(serializers.Serializer[dict[str, Any]]):
    scheme = serializers.ChoiceField(["fp-v1"])
    components = serializers.DictField(child=serializers.CharField(max_length=64))


class ActivateRequestSerializer(serializers.Serializer[dict[str, Any]]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # "instance" is an attribute of DRF serializers, so the fields are listed here.
        return {
            "license_key": serializers.CharField(
                max_length=64, allow_blank=True, trim_whitespace=False
            ),
            "trial": serializers.BooleanField(required=False, default=False),
            "product": ProductSerializer(),
            "instance": InstanceSerializer(),
            "fingerprint": FingerprintSerializer(),
            "device_pubkey": serializers.CharField(max_length=64),
            "client_time": serializers.DateTimeField(),
            "usage": serializers.DictField(required=False),
        }
