from rest_framework import serializers
from django.contrib.auth.models import Group
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'password']
        
    def perform_create(self, validated_data):
        # Make sure username is set from email
        validated_data['username'] = validated_data.get('email')
        return super().perform_create(validated_data)

class CustomUserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ['id', 'email', 'groups','username', 'first_name', 'last_name', 'phone_number', 'phone_uuid', 'laptop_uuid']

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']