from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RegisterSerializer, CreateGroupSerializer, AssignGroupSerializer
from .services import register_user
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import Permission, Group
from django.contrib.auth import get_user_model
from .models import BusinessUser


class RegisterAPI(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user, error = register_user(
            data["username"],
            data["email"],
            data["password"]
        )

        if error:
            return Response({"message": error}, status=400)

        return Response({"message": "User created"}, status=201)


class MeAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff
        })


class PermissionListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        perms = Permission.objects.select_related("content_type").all()

        data = [
            {
                "id": p.id,
                "name": p.name,
                "codename": f"{p.content_type.app_label}.{p.codename}",
                "app": p.content_type.app_label,
                "model": p.content_type.model
            }
            for p in perms
        ]

        return Response(data)


class CreateGroupAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        group_name = serializer.validated_data["group_name"]
        perm_codes = serializer.validated_data["permissions"]

        group, _ = Group.objects.get_or_create(name=group_name)

        permissions = []
        for code in perm_codes:
            app_label, codename = code.split(".")
            perm = Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename
            )
            permissions.append(perm)

        group.permissions.set(permissions)
        group.save()

        return Response(
            {"message": "Group created and permissions assigned"},
            status=status.HTTP_201_CREATED
        )


class AssignGroupToUserAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AssignGroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        group_name = serializer.validated_data["group_name"]

        User = get_user_model()
        user = User.objects.get(username=username)
        group = Group.objects.get(name=group_name)

        user.groups.add(group)

        return Response({"message": "Group assigned to user"})



class SyncBusinessUserAPI(APIView):
    def post(self, request):
        business_user_id = request.data.get("business_user_id")

        if not business_user_id:
            return Response({"error": "business_user_id required"}, status=400)

        user, created = BusinessUser.objects.update_or_create(
            business_user_id=business_user_id,
            defaults={
                "name": request.data.get("name"),
                "email": request.data.get("email"),
                "phone": request.data.get("phone")
            }
        )

        return Response({
            "status": "created" if created else "updated",
            "business_user_id": user.business_user_id
        })
