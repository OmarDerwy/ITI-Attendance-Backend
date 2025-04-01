from . import models, serializers
from rest_framework import viewsets, permissions
from core import permissions as core_permissions
from rest_framework.generics import RetrieveUpdateAPIView
from django.contrib.auth.models import Group
from rest_framework.decorators import action
from rest_framework.response import Response
from .helpers import getGroupIDFromNames
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken



class UserViewSet(viewsets.ModelViewSet):
    queryset = models.CustomUser.objects.all().order_by('id')
    http_method_names = ['get', 'put', 'patch', 'delete', 'post']
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return serializers.UserCreateSerializer
        return serializers.CustomUserSerializer

    # get and change groups of user
    @action(detail=True, methods=['get', 'patch', 'put', 'delete'], url_path='groups')
    def user_groups(self, request, *args, **kwargs):
        user = self.get_object()
        
        # GET request to retrieve groups
        if request.method == 'GET':
            groups = user.groups.all()
            serializer = serializers.GroupSerializer(groups, many=True)
            return Response(serializer.data)
        
        # PATCH request to add groups to user
        elif request.method == 'PATCH':
            groups = request.data.get('groups', [])
            group_ids = getGroupIDFromNames(groups)
            if isinstance(group_ids, Response):
                return group_ids
            user.groups.add(*group_ids)
            added_groups = Group.objects.filter(id__in=group_ids)
            serializer = serializers.GroupSerializer(added_groups, many=True)
            return Response({'message': 'Groups added successfully', 'added_groups': serializer.data})
        # PUT request to replace all groups with new groups
        elif request.method == 'PUT':
            groups = request.data.get('groups', [])
            group_ids = getGroupIDFromNames(groups)
            if isinstance(group_ids, Response):
                return group_ids
            user.groups.clear()
            user.groups.add(*group_ids)
            added_groups = user.groups.all()
            serializer = serializers.GroupSerializer(added_groups, many=True)
            return Response({'message': 'Groups replaced successfully', 'current_groups': serializer.data})
        # DELETE request to remove groups from user
        elif request.method == 'DELETE':
            groups = request.data.get('groups', [])
            
            if not groups:
                if user.groups.exists():
                    user.groups.clear()
                    return Response({'message': 'All groups removed successfully'})
                else:
                    return Response({'message': 'User has no groups to remove'}, status=400)
            else:
                group_ids = getGroupIDFromNames(groups)
                if isinstance(group_ids, Response):
                    return group_ids
                existing_groups = user.groups.filter(id__in=group_ids)
                if not existing_groups.exists():
                    return Response({'message': 'User does not belong to the specified groups'}, status=400)
                
                user.groups.remove(*group_ids)
                current_groups = user.groups.all()
                serializer = serializers.GroupSerializer(current_groups, many=True)
                return Response({'message': 'Specified groups removed successfully', 'current_groups': serializer.data})



class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by('name')
    serializer_class = serializers.GroupSerializer
    permission_classes = [core_permissions.IsAdminUser]

class ResetPassword(APIView):
    permission_classes = [core_permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        if not email:
            raise ValidationError({'email': 'This field is required.'})

        try:
            user = models.CustomUser.objects.get(email=email)
        except models.CustomUser.DoesNotExist:
            raise ValidationError({'email': 'User with this email does not exist.'})

        token = access_token = AccessToken.for_user(user)

        reset_url = f"{request.build_absolute_uri('/reset-password-confirmation/')}{token}/"
        send_mail(
            subject="Password Reset Request",
            message=f"Click the link below to reset your password:\n{reset_url}",
            from_email="omarderwy@gmail.com",
            recipient_list=[email],
        )
        return Response({'message': 'Password reset email sent successfully.'})


class ResetPasswordConfirmation(APIView):
    permission_classes = [core_permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        token = kwargs.get('token')
        new_password = request.data.get('new_password')
        if not new_password:
            raise ValidationError({'new_password': 'This field is required.'})

        try:
            user = models.CustomUser.objects.get(email=request.data.get('email'))
        except models.CustomUser.DoesNotExist:
            raise ValidationError({'email': 'User with this email does not exist.'})

        try:
            access_token = AccessToken(token)
            if access_token['user_id'] != user.id:
                raise ValidationError({'token': 'Invalid token for the provided user.'})
        except Exception:
            raise ValidationError({'token': 'Invalid or expired token.'})

        user.set_password(new_password)
        user.save()
        return Response({'message': 'Password has been reset successfully.'})