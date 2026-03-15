from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsStaffOrAdmin

from .models import Order, OrderItem
from .serializers import OrderCancelSerializer, OrderSyncSerializer


class SyncOrderAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        serializer = OrderSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        User = get_user_model()
        try:
            user = User.objects.get(id=data["user_id"])
        except User.DoesNotExist:
            return Response({"error": "User khong ton tai"}, status=404)

        order, created = Order.objects.update_or_create(
            external_order_id=data["external_order_id"],
            defaults={
                "user": user,
                "status": data["status"],
                "total_amount": data["total_amount"],
            },
        )

        items = data.get("items", [])
        OrderItem.objects.filter(order=order).delete()
        if data["status"] != Order.STATUS_CANCELED:
            for item in items:
                OrderItem.objects.create(
                    order=order,
                    name=item["name"],
                    product_type=item.get("product_type"),
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                )

        return Response(
            {
                "message": "Order synced",
                "order_id": order.id,
                "external_order_id": order.external_order_id,
                "status": order.status,
                "created": created,
            },
            status=201 if created else 200,
        )


class CancelOrderAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrAdmin]

    def post(self, request):
        serializer = OrderCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        external_order_id = serializer.validated_data["external_order_id"]

        try:
            order = Order.objects.get(external_order_id=external_order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order khong ton tai"}, status=404)

        order.status = Order.STATUS_CANCELED
        order.save(update_fields=["status"])

        return Response(
            {
                "message": "Order canceled",
                "order_id": order.id,
                "external_order_id": order.external_order_id,
                "status": order.status,
            }
        )
