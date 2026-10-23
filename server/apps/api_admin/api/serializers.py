"""Admin API shapes; the console client is generated from the schema (npm run gen:api)."""

from typing import Any

from rest_framework import serializers


class SessionRequestSerializer(serializers.Serializer[dict[str, Any]]):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class SessionSerializer(serializers.Serializer[dict[str, Any]]):
    username = serializers.CharField()
    role = serializers.ChoiceField(["operator", "admin", "customer_viewer"])


class CustomerSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=512)
    inn = serializers.CharField(max_length=12, allow_blank=True)
    external_id = serializers.CharField(max_length=128, allow_blank=True)
    status = serializers.ChoiceField(["active", "archived"])
    created_at = serializers.DateTimeField(read_only=True)


class CustomerWriteSerializer(serializers.Serializer[dict[str, Any]]):
    """Fields an operator sends; checks of values are in licensing.domain (AGENTS.md, rule 2)."""

    name = serializers.CharField(max_length=512, required=False, allow_blank=True)
    inn = serializers.CharField(max_length=12, required=False, allow_blank=True)
    external_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    status = serializers.CharField(max_length=16, required=False)


class CustomerPageSerializer(serializers.Serializer[dict[str, Any]]):
    count = serializers.IntegerField()
    results = CustomerSerializer(many=True)


class CustomerQuerySerializer(serializers.Serializer[dict[str, Any]]):
    name = serializers.CharField(required=False, allow_blank=True, default="")
    inn = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(required=False, allow_blank=True, default="")
    ordering = serializers.CharField(required=False, default="name")
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)


class LicenseSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField()
    customer_id = serializers.UUIDField()
    customer_name = serializers.CharField()
    product_id = serializers.UUIDField()
    edition_id = serializers.UUIDField(allow_null=True)
    type = serializers.ChoiceField(["subscription", "perpetual", "trial", "nfr", "free"])
    status = serializers.ChoiceField(["active", "suspended", "revoked"])
    limit = serializers.IntegerField()
    reserve_pct = serializers.IntegerField(allow_null=True)
    valid_from = serializers.DateTimeField()
    valid_until = serializers.DateTimeField(allow_null=True)
    support_until = serializers.DateTimeField(allow_null=True)
    enforcement = serializers.CharField(allow_blank=True)
    monitor_until = serializers.DateTimeField(allow_null=True)
    policy_profile_code = serializers.CharField(allow_blank=True)
    rights_version = serializers.IntegerField()
    key_masks = serializers.ListField(child=serializers.CharField())


class LicensePageSerializer(serializers.Serializer[dict[str, Any]]):
    count = serializers.IntegerField()
    results = LicenseSerializer(many=True)


class LicenseQuerySerializer(serializers.Serializer[dict[str, Any]]):
    product_id = serializers.UUIDField(required=False)
    customer_id = serializers.UUIDField(required=False)
    status = serializers.CharField(required=False, allow_blank=True, default="")
    expires_before = serializers.DateTimeField(required=False)
    expires_after = serializers.DateTimeField(required=False)
    ordering = serializers.CharField(required=False, default="valid_until")
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)


class LicenseCreateSerializer(serializers.Serializer[dict[str, Any]]):
    customer_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    metric_id = serializers.UUIDField()
    type = serializers.CharField()
    limit = serializers.IntegerField()
    reserve_pct = serializers.IntegerField(required=False, allow_null=True)
    valid_from = serializers.DateTimeField()
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    support_until = serializers.DateTimeField(required=False, allow_null=True)
    policy_profile_code = serializers.CharField(required=False, allow_blank=True)
    enforcement = serializers.CharField(required=False, allow_blank=True)


class RenewSerializer(serializers.Serializer[dict[str, Any]]):
    valid_until = serializers.DateTimeField(allow_null=True)
    support_until = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer[dict[str, Any]]):
    reason = serializers.CharField(max_length=1000, allow_blank=True)


class LiftBlockSerializer(ReasonSerializer):
    until = serializers.DateTimeField()


class SettingsSerializer(serializers.Serializer[dict[str, Any]]):
    limit = serializers.IntegerField(required=False)
    reserve_pct = serializers.IntegerField(required=False, allow_null=True)
    metric_id = serializers.UUIDField(required=False)
    enforcement = serializers.CharField(required=False, allow_blank=True)


class TransferSerializer(ReasonSerializer):
    customer_id = serializers.UUIDField()
    document = serializers.CharField(max_length=256, allow_blank=True, required=False, default="")


class IssuedKeySerializer(serializers.Serializer[dict[str, Any]]):
    license_id = serializers.UUIDField()
    key = serializers.CharField(help_text="Shown once; the server keeps only hash and mask")
    key_mask = serializers.CharField()


class UsageSerializer(serializers.Serializer[dict[str, Any]]):
    active = serializers.IntegerField()
    in_reserve = serializers.IntegerField()
    released_auto = serializers.IntegerField()
    conflicts = serializers.IntegerField()
    last_seen_at = serializers.DateTimeField(allow_null=True)
    by_version = serializers.DictField(child=serializers.IntegerField())
    by_os = serializers.DictField(child=serializers.IntegerField())


class HistoryEventSerializer(serializers.Serializer[dict[str, Any]]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        # "data" is an attribute of DRF serializers, so the fields are listed here.
        return {
            "seq": serializers.IntegerField(),
            "at": serializers.DateTimeField(),
            "actor": serializers.CharField(),
            "action": serializers.CharField(),
            "data": serializers.DictField(),
        }


class ActivationSerializer(serializers.Serializer[dict[str, Any]]):
    activation_id = serializers.CharField()
    license_id = serializers.UUIDField()
    instance_id = serializers.UUIDField()
    instance_name = serializers.CharField(allow_blank=True)
    subject_type = serializers.CharField()
    status = serializers.ChoiceField(["active", "released", "released_auto", "revoked", "conflict"])
    in_reserve = serializers.BooleanField()
    product_version = serializers.CharField()
    os = serializers.DictField()
    activated_at = serializers.DateTimeField()
    last_seen_at = serializers.DateTimeField()
    released_at = serializers.DateTimeField(allow_null=True)


class ActivationPageSerializer(serializers.Serializer[dict[str, Any]]):
    count = serializers.IntegerField()
    results = ActivationSerializer(many=True)


class ActivationQuerySerializer(serializers.Serializer[dict[str, Any]]):
    license_id = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(required=False, allow_blank=True, default="")
    ordering = serializers.CharField(required=False, default="-last_seen_at")
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=20)


class EditionSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.DictField(child=serializers.CharField())


class ProductSerializer(serializers.Serializer[dict[str, Any]]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.DictField(child=serializers.CharField())
    default_metric_id = serializers.UUIDField()
    default_metric = serializers.CharField()
    editions = EditionSerializer(many=True)
