"""Request and response shapes of Product API v1 (contracts/openapi-product-api-v1.yaml)."""

from typing import Any

from rest_framework import serializers

# contracts/schemas/license-state.schema.json
LICENSE_STATES = [
    "TRIAL",
    "ACTIVE",
    "UNLICENSED",
    "RESTRICTED",
    "REVOKED",
    "NOTICE",
    "GRACE",
    "BLOCKED",
]


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


class CheckOsSerializer(serializers.Serializer[dict[str, Any]]):
    os = OsInfoSerializer()
    name = serializers.CharField(max_length=128, required=False, allow_blank=True)


class CheckRequestSerializer(serializers.Serializer[dict[str, Any]]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # "instance" is an attribute of DRF serializers, so the fields are listed here.
        return {
            "lease_seq": serializers.IntegerField(min_value=0),
            "product": ProductSerializer(),
            "instance": CheckOsSerializer(),
            "fingerprint": FingerprintSerializer(required=False),
            "state": serializers.ChoiceField(LICENSE_STATES),
            "usage": serializers.DictField(required=False),
            "acked_directives": serializers.ListField(
                child=serializers.CharField(max_length=64), required=False, default=list
            ),
            "unsupported_directives": serializers.ListField(
                child=serializers.CharField(max_length=64), required=False, default=list
            ),
            "client_time": serializers.DateTimeField(),
            "last_success_at": serializers.DateTimeField(required=False),
        }


class ReleaseRequestSerializer(serializers.Serializer[dict[str, Any]]):
    reason = serializers.ChoiceField(["uninstall", "user", "transfer", "directive"])
    client_time = serializers.DateTimeField()


class OfflineActivateSerializer(serializers.Serializer[dict[str, Any]]):
    """Payload of .alk-req type activate (contracts/schemas/alk-req.schema.json)."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        return {
            "license_key": serializers.CharField(max_length=64, trim_whitespace=False),
            "product": ProductSerializer(),
            "instance": InstanceSerializer(),
            "fingerprint": FingerprintSerializer(),
            "device_pubkey": serializers.CharField(max_length=64),
        }


class OfflineDeviceSerializer(serializers.Serializer[dict[str, Any]]):
    """Payload of .alk-req types renew and release."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        return {
            "activation_id": serializers.CharField(max_length=30),
            "product": ProductSerializer(),
            "instance": InstanceSerializer(),
            "fingerprint": FingerprintSerializer(),
            "device_pubkey": serializers.CharField(max_length=64),
            "usage": serializers.DictField(required=False),
        }
