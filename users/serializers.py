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
        fields = ["id", "username", "email", "role", "is_staff", "is_active"]


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
