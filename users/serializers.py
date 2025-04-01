from rest_framework import serializers
from django.contrib.auth.models import Group
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from django.contrib.auth import get_user_model
from rest_framework.settings import api_settings
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions

User = get_user_model()

class UserCreateSerializer(BaseUserCreateSerializer):
    groups = serializers.SlugRelatedField(
        queryset=Group.objects.all(),
        slug_field='name',
        many=True,
        required=False
    )
    # class Meta(BaseUserCreateSerializer.Meta):
    #     model = User
    #     fields = ['id', 'email', 'password', 'groups']
    
    def validate(self, attrs):
        groups = attrs.pop('groups', None)
        user = User(**attrs)
        attrs['groups'] = groups if groups else []
        password = attrs.get("password")

        try:
            validate_password(password, user)
        except django_exceptions.ValidationError as e:
            serializer_error = serializers.as_serializer_error(e)
            raise serializers.ValidationError(
                {"password": serializer_error[api_settings.NON_FIELD_ERRORS_KEY]}
            )

        return attrs

class CustomUserSerializer(BaseUserSerializer):
    groups = serializers.StringRelatedField(many=True)
    class Meta(BaseUserSerializer.Meta):
        model = User
        fields = ['id', 'email', 'groups', 'first_name', 'last_name', 'phone_number', 'student_info', 'is_staff', 'is_superuser']
        read_only_fields = ['id', 'email', 'groups', 'phone_number', 'student_info',] # TODO create more specific permissions later
    

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class UserActivateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['is_active']