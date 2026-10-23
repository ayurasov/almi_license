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
