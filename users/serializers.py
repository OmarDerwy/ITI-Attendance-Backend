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
        fields = ['id', 'email', 'groups', 'first_name', 'last_name', 'phone_number', 'is_staff', 'is_superuser', 'is_active']
        read_only_fields = ['id', 'email', 'groups', 'phone_number'] # TODO create more specific permissions later
    

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']

class UserActivateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['is_active']

class StudentsSerializer(serializers.ModelSerializer):
    tracks = serializers.StringRelatedField(source='student_profile.track')

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone_number', 'tracks', 'is_active', 'date_joined']
        read_only_fields = ['id', 'email'] # TODO create more specific permissions later

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['groups'] = [group.name for group in instance.groups.all()]
        return representation
    def to_internal_value(self, data):
        internal_value = super().to_internal_value(data)
        track = data.get('track')
        if track:
            try:
                track_id = int(track)
                internal_value['student_profile'] = {'track': track_id}
            except ValueError:
                raise serializers.ValidationError({'track': 'Track ID must be an integer.'})
        return internal_value