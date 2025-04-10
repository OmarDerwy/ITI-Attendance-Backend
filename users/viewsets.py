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
from django.db.models import Q
# import from attendance_management
from attendance_management import models as attend_models



class UserViewSet(viewsets.ModelViewSet):
    queryset = models.CustomUser.objects.all().order_by('id')
    http_method_names = ['get', 'put', 'patch', 'delete', 'post']
    permission_classes = [core_permissions.IsInstructorOrAboveUser]

    # def get_queryset(self):               #deprecated
    #     user = self.request.user
    #     userGroups = user.groups.all()
    #     if 'supervisor' in userGroups.values_list('name', flat=True):
    #         # If the user is a supervisor, filter the queryset to only include their students
    #         hisTrack = user.tracks.get()
    #         StudentObjs = models.CustomUser.objects.filter(student_profile__track=hisTrack)
    #         return StudentObjs.order_by('id')
    #     return models.CustomUser.objects.all().order_by('id')
    

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return serializers.UserCreateSerializer
        return serializers.CustomUserSerializer
    @action(detail=False, methods=['get'], url_path='students')
    def students_list(self, request):
        group = Group.objects.get(name="student")
        data = self.get_queryset().filter(groups=group)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='instructors')
    def instructors_list(self, request):
        group = Group.objects.get(name="instructor")
        data = self.get_queryset().filter(groups=group)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='supervisors')
    def supervisors_list(self, request):
        group = Group.objects.get(name="supervisor")
        data = self.get_queryset().filter(groups=group)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='admins')
    def admins_list(self, request):
        group = Group.objects.get(name="admin")
        data = self.get_queryset().filter(groups=group)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='admins-and-supervisors')
    def admins_supervisors_list(self, request):
        group = Group.objects.filter(name__in=["admin", "supervisor"])
        data = self.get_queryset().filter(groups__in=group).distinct()
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    # use this endpoint to add new user (admin/supervisor)
    def create(self, request, *args, **kwargs):
        # Check supervisor permissions
        request_user = self.request.user
        if not request_user.groups.filter(name='admin').exists():        # .all().values_list('name', flat=True):
            return Response({'error': 'You do not have permission to create users'}, status=403)
        
        # Extract required data
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=400)
        
        # Create the user with basic information
        password = 'test'  # In production: get_random_string(length=8)
        user = models.CustomUser.objects.create_user(
            email=email,
            password=password,
            is_active=False,
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
        )
        
        # Add user group
        groups = request.data.get('groups', [])
        user_group = Group.objects.get(name=groups[0])  # Access the first group in the list
        user.groups.add(user_group)
        
        # Create activation token and URL
        access_token = AccessToken.for_user(user)
        create_password_url = f"http://localhost:8080/activate/{access_token}/"
        
        # For development: print the link
        print(f"Confirmation link for {email}: {create_password_url}")
        
        # For production: send email (commented out)
        # send_mail(
        #     subject="Account Activation",
        #     message=f"Click the link below to activate your account:\n{create_password_url}",
        #     from_email="omarderwy@gmail.com",
        #     recipient_list=[email],
        # )
        
        # Serialize and return the created user
        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'confirmation_link': create_password_url
        }, status=201)
        
    # update user
    def update(self, request, *args, **kwargs):
        
        request_user = self.request.user
        if not request_user.groups.filter(name='admin').exists():        # .all().values_list('name', flat=True):
            return Response({'error': 'You do not have permission to update users'}, status=403)
        
        user = self.get_object()
        email = request.data.get('email')
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        groups = request.data.get('groups', [])

        # Check if email has changed
        if email and email != user.email:
            user.email = email
            user.is_active = False  # Deactivate user until they confirm the new email
            password = 'test'  # In production: get_random_string(length=8)
            user.set_password(password)

            # Create activation token and URL
            access_token = AccessToken.for_user(user)
            create_password_url = f"http://localhost:8080/activate/{access_token}/"

            # For development: print the link
            print(f"Confirmation link for {email}: {create_password_url}")

            # For production: send email (commented out)
            # send_mail(
            #     subject="Account Activation",
            #     message=f"Click the link below to activate your account:\n{create_password_url}",
            #     from_email="omarderwy@gmail.com",
            #     recipient_list=[email],
            # )

        # Update first and last name
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name

        # Update groups if provided
        if groups:
            group_ids = getGroupIDFromNames(groups)
            if isinstance(group_ids, Response):
                return group_ids
            user.groups.clear()
            user.groups.add(*group_ids)

        user.save()

        # Serialize and return the updated user
        serializer = self.get_serializer(user)
        return Response(serializer.data)
            
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
    permission_classes = []

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        if not email:
            raise ValidationError({'email': 'This field is required.'})

        try:
            user = models.CustomUser.objects.get(email=email)
        except models.CustomUser.DoesNotExist:
            raise ValidationError({'email': 'User with this email does not exist.'})

        token = AccessToken.for_user(user)

        reset_url = f"http://localhost:8080/reset-password/{user.id}/{token}/"
        # send_mail(
        #     subject="Password Reset Request",
        #     message=f"Click the link below to reset your password:\n{reset_url}",
        #     from_email="omarderwy@gmail.com",
        #     recipient_list=[email],
        # )
        print(f"Password reset link for {email}: {reset_url}")
        return Response({'message': 'Password reset email sent successfully.',
                        'reset_url': reset_url})


class ResetPasswordConfirmation(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        new_password = request.data.get('newPassword')
        userId = request.data.get('userId')
        if not new_password:
            raise ValidationError({'new_password': 'This field is required.'})

        try:
            user = models.CustomUser.objects.get(id=userId)
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

class StudentViewSet(viewsets.ModelViewSet):

    serializer_class = serializers.StudentsSerializer
    permission_classes = [core_permissions.IsSupervisorOrAboveUser]

    def get_paginated_response(self, data):
        # add a count of is_active students
        queryset = self.get_queryset()
        active_students = queryset.filter(is_active=True).count()
        inactive_students = queryset.filter(is_active=False).count()

        response = super().get_paginated_response(data)
        response.data['active_users'] = active_students
        response.data['inactive_users'] = inactive_students

        return response

    def get_queryset(self):
        requestUser = self.request.user
        requestUserGroups = requestUser.groups.all()
        allUsers = models.CustomUser.objects.all()
        searchParam = self.request.query_params.get('search', None)
        students = allUsers.filter(groups__name='student') # TODO not all students actually possess the student group, need to fix database later
        if searchParam:
            students = students.filter(Q(email__icontains=searchParam) | Q(first_name__icontains=searchParam) | Q(last_name__icontains=searchParam)) # TODO consider adding capability for admins to view all students and add them
        if 'supervisor' in requestUserGroups.values_list('name', flat=True):
            hisTrack = requestUser.tracks.all()
            students = students.filter(student_profile__track__in=hisTrack)
            return students.order_by('id')
        return students.order_by('id')

    def create(self, request, *args, **kwargs):
        # Check supervisor permissions
        request_user = self.request.user
        if 'supervisor' not in request_user.groups.all().values_list('name', flat=True):
            return Response({'error': 'You do not have permission to create users'}, status=403)
        
        # Get the track object from the body
        track_id = request.data.get('track_id')
        if not track_id:
            return Response({'error': 'Track ID is required'}, status=400)
        track_obj = request_user.tracks.get(id=track_id)
        # track_obj = request_user.tracks.first()
        if not track_obj:
            return Response({'error': 'You are not currently the supervisor of any track'}, status=400)
        
        # Extract required data
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=400)
        
        # Create the user with basic information
        password = 'test'  # In production: get_random_string(length=8)
        user = models.CustomUser.objects.create_user(
            email=email,
            password=password,
            is_active=False,
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
        )
        
        # Create student profile and associate with track
        student_profile = attend_models.Student.objects.create(track=track_obj, user=user)
        
        # Add student group
        student_group = Group.objects.get(name='student')
        user.groups.add(student_group)
        
        # Create activation token and URL
        access_token = AccessToken.for_user(user)
        create_password_url = f"http://localhost:8080/activate/{access_token}/"
        
        # For development: print the link
        print(f"Confirmation link for {email}: {create_password_url}")
        
        # For production: send email (commented out)
        # send_mail(
        #     subject="Account Activation",
        #     message=f"Click the link below to activate your account:\n{create_password_url}",
        #     from_email="omarderwy@gmail.com",
        #     recipient_list=[email],
        # )
        
        # Serialize and return the created user
        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'confirmation_link': create_password_url
        }, status=201)

class BulkCreateStudents(APIView):
    permission_classes = [core_permissions.IsSupervisorOrAboveUser]
    http_method_names = ['post']

    confirmation_links = {}
    def post(self, request, *args, **kwargs):
        requestUser = self.request.user
        requestUserGroups = requestUser.groups.all()
        data = request.data
        users = data.get('users', [])
        if not users:
            return Response({'error': 'No user data provided'}, status=400)
        if 'supervisor' not in requestUserGroups.values_list('name', flat=True):
            return Response({'error': 'You do not have permission to create users'}, status=403)
        for user_data in users:
            email = user_data.get('email')
            # groups = user_data.get('groups', [])
            first_name = user_data.get('first_name')
            last_name = user_data.get('last_name')
            phone_number = user_data.get('phone_number')
            track = user_data.get('track_id')

            # find track
            track_obj = requestUser.tracks.get(id=track) if track else None
            if not track_obj:
                return Response({'error': f'You currently arent the supervisor of any track.'}, status=400)

            print(f"Creating user with email: {email}, track: {track_obj}, track_name: {track_obj}")

            if not email:
                return Response({'error': 'Email is required for all users'}, status=400)
            # create random password ( uncomment this in production)
            # password = get_random_string(length=8)
            password = 'test'
            print(f"Generated password for {email}: {password}")
            # Create the user
            user = models.CustomUser.objects.create_user(
                email=email,
                password=password,
                is_active=False,
                first_name=first_name,
                last_name=last_name,
                phone_number=phone_number
            )

            # create student_profile
            student_profile = attend_models.Student.objects.create(track=track_obj, user=user)
            student_profile.save()

            # add student group to user
            studentGroup = Group.objects.get(name='student')
            user.groups.add(studentGroup)

            # create tokens for users
            access_token = AccessToken.for_user(user)
            create_password_url= f"http://localhost:8080/activate/{access_token}/"

            # aggregate confirmation links
            print(f"Confirmation link for {email}: {create_password_url}")
            self.confirmation_links[email] = create_password_url
            
            # uncomment this in production
            # send_mail(
            #     subject="Password Reset Request",
            #     message=f"Click the link below to activate your account:\n{create_password_url}",
            #     from_email="omarderwy@gmail.com",
            #     recipient_list=[email],
            # )


        return Response({'message': 'Bulk user creation successful!', 'confirmation_links': self.confirmation_links})

class UserActivateView(APIView):
    permission_classes = [permissions.AllowAny]

    def patch(self, request):
        token = request.data.get('token')
        token = token['token']
        if not token:
            raise ValidationError({'token': 'This field is required.'})

        try:
            access_token = AccessToken(bytes(token, 'utf-8'))
            user_id = access_token['user_id']
            user = models.CustomUser.objects.get(id=user_id)
        except models.CustomUser.DoesNotExist:
            raise ValidationError({'error': 'User does not exist.'})
        except Exception:
            raise ValidationError({'token': 'Invalid or expired token.'})

        if user.is_active:
            return Response({'message': 'User is already active.'}, status=400)

        user.is_active = True
        user.save()
        return Response({'message': 'User has been activated successfully.'})
