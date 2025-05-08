from datetime import timezone
from . import models, serializers
from rest_framework import viewsets, permissions, status
from core import permissions as core_permissions
from django.contrib.auth.models import Group
from rest_framework.decorators import action
from rest_framework.response import Response
from .helpers import getGroupIDFromNames
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from django.db.models import Q
# import from attendance_management
from attendance_management import models as attend_models
import os

# Load environment variables
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:8080')
ACTIVATION_PATH = os.environ.get('ACTIVATION_PATH', '/activate/')
RESET_PASSWORD_PATH = os.environ.get('RESET_PASSWORD_PATH', '/reset-password/')

class AbstractUserViewSet(viewsets.ModelViewSet):
    """
    Abstract base viewset for user operations.
    The create and update methods return the user object for further processing.
    Handles sending activation emails on create and update.
    """

    def create(self, request, *args, **kwargs):
        # Extract required data
        email = request.data.get('email')
        if not email:
            raise ValidationError({'error': 'Email is required'})
        password = 'test'  # In production: get_random_string(length=8)
        user = models.CustomUser.objects.create_user(
            email=email,
            password=password,
            is_active=False,
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
        )
        groups = request.data.get('groups', [])
        if groups:
            user_group = Group.objects.get(name=groups[0])
            user.groups.add(user_group)
        # Send activation email
        self._send_confirmation_mail(user)
        return user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        email = request.data.get('email')
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        groups = request.data.get('groups', [])

        email_changed = False
        if email and email != user.email:
            user.email = email #TODO email is changed before verification, need to store the old email somwhere
            user.is_active = False
            password = 'test'  # In production: get_random_string(length=8)
            user.set_password(password)
            email_changed = True
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if groups:
            group_ids = getGroupIDFromNames(groups)
            if isinstance(group_ids, Response):
                return group_ids
            user.groups.clear()
            user.groups.add(*group_ids)
        user.save()
        # Send activation email if email changed
        if email_changed:
            self._send_confirmation_mail(user)
        return user

    def _send_confirmation_mail(self, user):
        access_token = AccessToken.for_user(user)
        create_password_url = f"{FRONTEND_BASE_URL}{ACTIVATION_PATH}{access_token}/"
        print(f"Confirmation link for {user.email}: {create_password_url}")
        send_mail(
            subject="Account Activation",
            message=f"Click the link below to activate your account:\n{create_password_url}",
            from_email=os.environ.get('EMAIL_USER'),
            recipient_list=[os.environ.get('RECIPIENT_EMAIL')],
        )

class UserViewSet(AbstractUserViewSet):
    queryset = models.CustomUser.objects.all().order_by('id')
    http_method_names = ['get', 'put', 'patch', 'delete', 'post']
    permission_classes = [core_permissions.IsInstructorOrAboveUser]

    def get_queryset(self):
        return models.CustomUser.objects.all().order_by('id').prefetch_related('groups', 'student_profile')

    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return serializers.UserCreateSerializer
        return serializers.CustomUserSerializer

    @action(detail=False, methods=['get'], url_path='students')
    def students_list(self, request):
        group = Group.objects.get(name="student")
        data = self.get_queryset().filter(groups=group, is_active=True).prefetch_related('groups')
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='instructors')
    def instructors_list(self, request):
        group = Group.objects.get(name="instructor")
        data = self.get_queryset().filter(groups=group, is_active=True).prefetch_related('groups')
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='supervisors')
    def supervisors_list(self, request):
        group = Group.objects.get(name="supervisor")
        data = self.get_queryset().filter(groups=group).prefetch_related('groups')
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='admins')
    def admins_list(self, request):
        group = Group.objects.get(name="admin")
        data = self.get_queryset().filter(groups=group).prefetch_related('groups')
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='admins-and-supervisors')
    def admins_supervisors_list(self, request):
        group = Group.objects.filter(name__in=["admin", "supervisor"])
        data = self.get_queryset().filter(groups__in=group).distinct().prefetch_related('groups')
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        user = super().create(request, *args, **kwargs)
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        # access_token = AccessToken.for_user(user)
        # create_password_url = f"{FRONTEND_BASE_URL}{ACTIVATION_PATH}{access_token}/"
        # return Response({
        #     'user': serializer.data,
        #     'confirmation_link': create_password_url
        # }, status=status.HTTP_201_CREATED)
        
    def update(self, request, *args, **kwargs):
        user = super().update(request, *args, **kwargs)
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
            
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

    @action(detail=False, methods=['POST'], url_path='change-password', permission_classes=[permissions.IsAuthenticated])
    def change_password(self, request):
        """
        Endpoint to change a user's password.
        Requires old_password and new_password in the request body.
        Validates that the old password is correct before changing to the new password.
        """
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        
        # Validate input data
        if not old_password or not new_password:
            return Response(
                {"error": "Both old_password and new_password are required."}, 
                status=400
            )
            
        # Check if old password is correct
        if not user.check_password(old_password):
            return Response(
                {"error": "Current password is incorrect."}, 
                status=400
            )
        
        try:
            # Set new password
            user.set_password(new_password)
            # Save with update_fields to ensure we only update the password field
            user.save(update_fields=['password'])
            
            # Generate a new token for the user
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            
            return Response({
                "message": "Password changed successfully.",
                "user_email": user.email,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
            }, status=200)
        except Exception as e:
            return Response({
                "error": f"An error occurred while changing password. Please contact support.",
                "detail": str(e)
            }, status=500)

    @action(detail=False, methods=['POST'], url_path='update-photo', permission_classes=[permissions.IsAuthenticated])
    def update_profile_photo(self, request):
        """
        Update the user's profile photo URL.
        
        Request body should contain:
        - photo_url: URL of the profile photo
        """
        user = request.user
        photo_url = request.data.get('photo_url')
        
        if not photo_url:
            return Response({"error": "photo_url is required."}, status=400)
        
        try:
            user.photo_url = photo_url
            user.save(update_fields=['photo_url'])
            
            return Response({
                "message": "Profile photo updated successfully.",
                "photo_url": user.photo_url
            }, status=200)
        except Exception as e:
            return Response({
                "error": f"An error occurred while updating profile photo: {str(e)}"
            }, status=500)

    @action(detail=False, methods=['GET'], url_path='photo', permission_classes=[permissions.IsAuthenticated])
    def get_profile_photo(self, request):
        """
        Retrieve just the profile picture URL of the currently authenticated user.
        
        Returns only the photo_url field for simpler API consumption.
        """
        user = request.user
        
        return Response({
            "photo_url": user.photo_url
        }, status=200)

    @action(detail=False, methods=['GET'], url_path='profile', permission_classes=[permissions.IsAuthenticated])
    def get_profile(self, request):
        """
        Retrieve the profile of the currently authenticated user.
        
        Returns all user data including photo URL and other profile fields.
        """
        # Get current user object
        user = request.user
        
        # Serialize the user data
        serializer = self.get_serializer(user)
        
        return Response(serializer.data, status=200)

class CoordinatorViewSet(AbstractUserViewSet):
    queryset = models.CustomUser.objects.filter(groups__name='coordinator').order_by('id')
    serializer_class = serializers.CustomUserSerializer
    permission_classes = [core_permissions.IsBranchManagerOrAboveUser]

    def get_queryset(self):
        requestUser = self.request.user
        requestUserGroups = requestUser.groups.values_list('name', flat=True)
        if 'admin' in requestUserGroups:
            return self.queryset
        if 'branch-manager' in requestUserGroups:
            requestUserBranches = requestUser.branches.values_list('id', flat=True)
            return self.queryset.filter(coordinator__branch__in=requestUserBranches).order_by('id')
        return self.queryset.none()
    def create(self, request, *args, **kwargs):
        user = super().create(request, *args, **kwargs)
        coordinator = attend_models.Coordinator.objects.create(user=user)
        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'coordinator_id': coordinator.id
        }, status=status.HTTP_201_CREATED)
    def update(self, request, *args, **kwargs): #TODO add things to change in the coordinator profile
        user = super().update(request, *args, **kwargs)
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

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

        reset_url = f"{FRONTEND_BASE_URL}{RESET_PASSWORD_PATH}{user.id}/{token}/"
        send_mail(
            subject="Account Activation",
            message=f"Click the link below to activate your account:\n{reset_url}",
            from_email=os.environ.get('EMAIL_USER'),
            recipient_list=[os.environ.get('RECIPIENT_EMAIL')],
        )
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

class StudentViewSet(AbstractUserViewSet):

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
        requestUserGroups = requestUser.groups.values_list('name', flat=True)
        allUsers = models.CustomUser.objects.all()
        searchParam = self.request.query_params.get('search', None)
        trackParam = self.request.query_params.get('track', None) # Use Only if user is a supervisor
        isactiveParam = self.request.query_params.get('is_active', None) # Use Only if user is a supervisor
        students = allUsers.filter(groups__name='student') # TODO not all students actually possess the student group, need to fix database later
        # select_related for performance
        students = students.select_related('student_profile', 'student_profile__track', 'student_profile__track__default_branch')
        if trackParam and trackParam != 'All':
            track = requestUser.tracks.get(id=trackParam)
            students = allUsers.filter(student_profile__track=track)
        if searchParam:
            students = students.filter(Q(email__icontains=searchParam) | Q(first_name__icontains=searchParam) | Q(last_name__icontains=searchParam)) # TODO consider adding capability for admins to view all students and add them
        if isactiveParam:
            isactiveParam = isactiveParam.lower() == 'true' if isactiveParam else False
            students = students.filter(student_profile__track__is_active=isactiveParam)
        if 'coordinator' in requestUserGroups:
            branch = requestUser.coordinator.branch
            students = students.filter(student_profile__track__default_branch=branch)
            return students.order_by('id')
        if 'supervisor' in requestUserGroups:
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
        if not track_obj:
            return Response({'error': 'You are not currently the supervisor of any track'}, status=400)

        # Use AbstractUserViewSet's create to create the user and send email
        user = super().create(request, *args, **kwargs)

        # Create student profile and associate with track
        student_profile = attend_models.Student.objects.create(track=track_obj, user=user)

        # Serialize and return the created user
        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'student_profile_id': student_profile.id
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs): #TODO add things to change in the student profile
        # Use AbstractUserViewSet's update to update the user and send email if needed
        user = super().update(request, *args, **kwargs)
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='make-inactive')
    def make_inactive(self, request, *args, **kwargs):
        student = self.get_object()
        student.is_active = False
        student.is_banned = True
        # delete attendance future records for user if they exist
        student_profile = student.student_profile
        upcoming_attendance_records =  student_profile.attendance_records.filter(schedule__created_at__gte=timezone.localtime())
        print(f"Deleting {upcoming_attendance_records.count()} attendance records for {student.email}.")
        upcoming_attendance_records.delete()
        student.save()
        return Response({'message': 'Student has been made inactive successfully.'})
    
    @action(detail=True, methods=['get'], url_path='resend-activation')
    def resend_activation(self, request, *args, **kwargs):
        student = self.get_object()
        student.is_banned = False
        if student.is_active:
            return Response({'message': 'User is already active.'}, status=400)
        self._send_confirmation_mail(student)
        return Response({
            'confirmation_link': create_password_url
        })

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
            create_password_url= f"{FRONTEND_BASE_URL}{ACTIVATION_PATH}{access_token}/"

            # aggregate confirmation links
            print(f"Confirmation link for {email}: {create_password_url}")
            self.confirmation_links[email] = create_password_url
            
            # uncomment this in production
            send_mail(
                subject="Account Activation",
                message=f"Click the link below to activate your account:\n{create_password_url}",
                from_email=os.environ.get('EMAIL_USER'),
                recipient_list=[os.environ.get('RECIPIENT_EMAIL')],
            )


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
        if 'student' in user.groups.all().values_list('name', flat=True):
            student_profile = attend_models.Student.objects.get(user=user)
            # check for upcoming schedules and create attendance records for user if they don't exist
            upcoming_schedules = attend_models.Schedule.objects.filter(track=student_profile.track, start_time__gte=timezone.localtime())
            numOfAttenCreated = 0
            for schedule in upcoming_schedules:
                record, created = attend_models.AttendanceRecord.objects.get_or_create(student=student_profile, schedule=schedule)
                if created:
                    numOfAttenCreated += 1
            print(f"Created {numOfAttenCreated} attendance records for {user.email}.")
            return Response({'message': 'User has been activated successfully.', 'attendance_records_created': numOfAttenCreated})
        return Response({'message': 'User has been activated successfully.'})
    
class TokenBlacklistViewAll(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({'error': 'User is not authenticated.'}, status=401)

        # Get all tokens for the user and blacklist them
        tokens = OutstandingToken.objects.filter(user_id=user)
        for token in tokens:
            token.blacklist()

        return Response({'message': 'All tokens have been blacklisted successfully.'})