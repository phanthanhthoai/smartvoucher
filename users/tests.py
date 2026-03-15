from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from .views import CustomerListAPI, UpdateUserPermissionsAPI, UpdateUserRoleAPI


class UserAuthorizationTests(TestCase):
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

    def test_staff_can_get_customer_list(self):
        request = self.factory.get("/api/users/customers/")
        force_authenticate(request, user=self.staff_user)

        response = CustomerListAPI.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["role"], "customer")

    def test_customer_cannot_get_customer_list(self):
        request = self.factory.get("/api/users/customers/")
        force_authenticate(request, user=self.customer_user)

        response = CustomerListAPI.as_view()(request)

        self.assertEqual(response.status_code, 403)

    def test_staff_can_update_user_role_and_is_staff_flag(self):
        request = self.factory.patch(
            f"/api/users/{self.customer_user.id}/role/",
            {"role": "staff"},
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = UpdateUserRoleAPI.as_view()(request, user_id=self.customer_user.id)

        self.customer_user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.customer_user.role, "staff")
        self.assertTrue(self.customer_user.is_staff)

    def test_staff_can_update_direct_permissions(self):
        permission = Permission.objects.first()
        self.assertIsNotNone(permission)

        request = self.factory.patch(
            f"/api/users/{self.customer_user.id}/permissions/",
            {
                "permissions": [
                    f"{permission.content_type.app_label}.{permission.codename}",
                ],
                "groups": [],
            },
            format="json",
        )
        force_authenticate(request, user=self.staff_user)

        response = UpdateUserPermissionsAPI.as_view()(request, user_id=self.customer_user.id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.customer_user.user_permissions.filter(id=permission.id).exists())
