from rest_framework import serializers


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
