from rest_framework import serializers
from .models import Voucher, UserVoucher, VoucherRule

class UserVoucherSerializer(serializers.ModelSerializer):
    voucher_title = serializers.CharField(source="voucher.title")
    discount_type = serializers.CharField(source="voucher.discount_type")
    discount_value = serializers.FloatField(source="voucher.discount_value")
    expiry_date = serializers.DateTimeField(source="voucher.expiry_date")
    remaining_uses = serializers.SerializerMethodField()

    class Meta:
        model = UserVoucher
        fields = [
            "id",
            "voucher_title",
            "discount_type",
            "discount_value",
            "expiry_date",
            "remaining_uses",
        ]

    def get_remaining_uses(self, obj):
        return 0 if obj.is_used else 1


class CheckVoucherSerializer(serializers.Serializer):
    voucher_code = serializers.CharField()
    order_total = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderSuccessEventSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=100)
    user_id = serializers.IntegerField(min_value=1)
    order_id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(choices=["paid", "success"])
    total_amount = serializers.FloatField(min_value=0)
    paid_at = serializers.DateTimeField(required=False)
    items = serializers.ListField(child=serializers.DictField(), allow_empty=False)


class VoucherRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoucherRule
        fields = [
            "required_role",
            "birthday_only",
            "min_order_amount",
            "min_items",
            "required_product_type",
            "period_type",
        ]


class CreateVoucherSerializer(serializers.ModelSerializer):
    code = serializers.CharField(required=False, allow_blank=True)
    rule = VoucherRuleSerializer()

    class Meta:
        model = Voucher
        fields = [
            "code",
            "title",
            "discount_type",
            "discount_value",
            "release_date",
            "expiry_date",
            "quantity",
            "event_type",
            "rule",
        ]

    def create(self, validated_data):
        rule_data = validated_data.pop("rule")
        code = validated_data.get("code")
        if code == "":
            validated_data.pop("code")
        voucher = Voucher.objects.create(**validated_data)
        VoucherRule.objects.create(voucher=voucher, **rule_data)
        return voucher


class CreateAndDistributeVoucherSerializer(CreateVoucherSerializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True
    )

    class Meta(CreateVoucherSerializer.Meta):
        fields = CreateVoucherSerializer.Meta.fields + ["user_ids"]

    def create(self, validated_data):
        user_ids = validated_data.pop("user_ids", None)
        voucher = super().create(validated_data)
        voucher._distribution_user_ids = user_ids
        return voucher


class UpdateVoucherSerializer(serializers.ModelSerializer):
    code = serializers.CharField(required=False, allow_blank=True)
    rule = VoucherRuleSerializer(required=False)

    class Meta:
        model = Voucher
        fields = [
            "code",
            "title",
            "discount_type",
            "discount_value",
            "release_date",
            "expiry_date",
            "quantity",
            "event_type",
            "rule",
        ]

    def update(self, instance, validated_data):
        rule_data = validated_data.pop("rule", None)
        code = validated_data.get("code")

        if code == "":
            validated_data.pop("code")

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if rule_data is not None:
            rule, _ = VoucherRule.objects.get_or_create(voucher=instance)
            for attr, value in rule_data.items():
                setattr(rule, attr, value)
            rule.save()

        return instance
