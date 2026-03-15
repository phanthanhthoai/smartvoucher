from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import UserVoucher, Voucher
from .views import VoucherRecipientListAPIView


class VoucherRecipientTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.User = get_user_model()
        self.staff_user = self.User.objects.create_user(
            username="staff1",
            email="staff@example.com",
            password="password123",
            role="staff",
            is_staff=True,
        )
        self.customer_user = self.User.objects.create_user(
            username="customer1",
            email="customer@example.com",
            password="password123",
            role="customer",
        )
        self.voucher = Voucher.objects.create(
            title="Welcome Voucher",
            discount_type="fixed",
            discount_value=10000,
            release_date=timezone.now(),
            expiry_date=timezone.now() + timedelta(days=30),
            quantity=100,
        )
        UserVoucher.objects.create(user=self.customer_user, voucher=self.voucher)

    def test_staff_can_view_voucher_recipients(self):
        request = self.factory.get(f"/api/vouchers/{self.voucher.id}/recipients/")
        force_authenticate(request, user=self.staff_user)

        response = VoucherRecipientListAPIView.as_view()(request, voucher_id=self.voucher.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["voucher"]["recipient_count"], 1)
        self.assertEqual(response.data["results"][0]["username"], "customer1")

    def test_customer_cannot_view_voucher_recipients(self):
        request = self.factory.get(f"/api/vouchers/{self.voucher.id}/recipients/")
        force_authenticate(request, user=self.customer_user)

        response = VoucherRecipientListAPIView.as_view()(request, voucher_id=self.voucher.id)

        self.assertEqual(response.status_code, 403)
