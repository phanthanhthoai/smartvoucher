from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import UserVoucher, Voucher
from .views import VoucherDetailAPIView, VoucherRecipientListAPIView


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

    def test_staff_can_update_unreleased_voucher(self):
        voucher = Voucher.objects.create(
            title="Future Voucher",
            discount_type="fixed",
            discount_value=5000,
            release_date=timezone.now() + timedelta(days=2),
            expiry_date=timezone.now() + timedelta(days=30),
            quantity=50,
        )
        request = self.factory.patch(
            f"/api/vouchers/{voucher.id}/",
            {"title": "Updated Future Voucher", "quantity": 80},
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = VoucherDetailAPIView.as_view()(request, voucher_id=voucher.id)

        voucher.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(voucher.title, "Updated Future Voucher")
        self.assertEqual(voucher.quantity, 80)

    def test_staff_cannot_update_released_voucher(self):
        request = self.factory.patch(
            f"/api/vouchers/{self.voucher.id}/",
            {"title": "Should Fail"},
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = VoucherDetailAPIView.as_view()(request, voucher_id=self.voucher.id)

        self.assertEqual(response.status_code, 400)

    def test_staff_can_delete_unreleased_voucher(self):
        voucher = Voucher.objects.create(
            title="Delete Me",
            discount_type="fixed",
            discount_value=5000,
            release_date=timezone.now() + timedelta(days=1),
            expiry_date=timezone.now() + timedelta(days=10),
            quantity=10,
        )
        request = self.factory.delete(f"/api/vouchers/{voucher.id}/")
        force_authenticate(request, user=self.staff_user)

        response = VoucherDetailAPIView.as_view()(request, voucher_id=voucher.id)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Voucher.objects.filter(id=voucher.id).exists())

    def test_staff_cannot_delete_released_voucher(self):
        request = self.factory.delete(f"/api/vouchers/{self.voucher.id}/")
        force_authenticate(request, user=self.staff_user)

        response = VoucherDetailAPIView.as_view()(request, voucher_id=self.voucher.id)

        self.assertEqual(response.status_code, 400)
