from django.contrib.auth import get_user_model
from rest_framework import serializers


User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class CreateGroupSerializer(serializers.Serializer):
    group_name = serializers.CharField()
    permissions = serializers.ListField(
        child=serializers.CharField()
    )


class AssignGroupSerializer(serializers.Serializer):
    username = serializers.CharField()
    group_name = serializers.CharField()


class UserSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", 
            "username", 
            "email",
            "phone",
            "role", 
            "is_staff", 
            "is_active", 
            "points", 
            "total_spent", 
            "date_joined",
            "last_login"
        ]


class UpdateUserRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=User.ROLE_CHOICES)


class UpdateUserPermissionsSerializer(serializers.Serializer):
    permissions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    groups = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "email", "phone", "points", "total_spent"]
        extra_kwargs = {
            "username": {"required": False},
            "email": {"required": False},
            "phone": {"required": False, "allow_blank": True, "allow_null": True},
            "points": {"required": False},
            "total_spent": {"required": False},
        }
