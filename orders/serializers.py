from rest_framework import serializers


class OrderItemInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    product_type = serializers.CharField(max_length=100, required=False, allow_blank=True, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.FloatField(min_value=0)


class OrderSyncSerializer(serializers.Serializer):
    external_order_id = serializers.CharField(max_length=100)
    user_id = serializers.IntegerField(min_value=1)
    status = serializers.ChoiceField(
        choices=["pending", "paid", "canceled"],
        required=False,
        default="pending",
    )
    total_amount = serializers.FloatField(min_value=0)
    items = OrderItemInputSerializer(many=True, allow_empty=True, required=False)


class OrderCancelSerializer(serializers.Serializer):
    external_order_id = serializers.CharField(max_length=100)
