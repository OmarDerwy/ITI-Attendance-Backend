from rest_framework import serializers
from django.contrib.auth.models import Group
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ['id', 'email', 'password']
        

class CustomUserSerializer(BaseUserSerializer):
    groups = serializers.StringRelatedField(many=True)
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ['id', 'email', 'groups', 'first_name', 'last_name', 'phone_number', 'phone_uuid', 'laptop_uuid', 'is_staff', 'is_superuser']
        read_only_fields = ['id', 'email', 'first_name', 'last_name', 'phone_number', 'phone_uuid', 'laptop_uuid']

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']