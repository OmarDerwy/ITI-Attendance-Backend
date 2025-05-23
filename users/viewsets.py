from django.utils import timezone
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
# import get_random_string
from django.utils.crypto import get_random_string
# import from attendance_management
from attendance_management import models as attend_models
import os

# Load environment variables
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:8080/')
ACTIVATION_PATH = os.environ.get('ACTIVATION_PATH', 'activate/')
RESET_PASSWORD_PATH = os.environ.get('RESET_PASSWORD_PATH', 'reset-password/')

class AbstractUserViewSet(viewsets.ModelViewSet):
    """
    Abstract base viewset for user operations.
    The create and update methods return the user object for further processing.
    Handles sending activation emails on create and update.
    """

    def create(self, request, *args, **kwargs):
        # Extract required data
        email = request.data.get('email')
        first_name=request.data.get('first_name')
        last_name=request.data.get('last_name')
        phone_number=request.data.get('phone_number')
        groups = kwargs.get('groups', request.data.get('groups', []))

        return NotImplementedError("This method should be implemented in the subclass")

    

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        email = request.data.get('email')
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        # Allow groups to be overridden via kwargs
        groups = kwargs.get('groups', request.data.get('groups', [])) #TODO of course of groups are changed like this, other models related to previous role need to be removed as well

        return NotImplementedError("This method should be implemented in the subclass")

    def _create_user(self, email, first_name, last_name, phone_number, groups):
        if not email:
            raise ValidationError({'error': 'Email is required'})
        user = models.CustomUser.objects.create_user(
            email=email,
            is_active=False,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
        )
        # Allow groups to be overridden via kwargs
        if groups:
            if isinstance(groups, str):
                groups = [groups]
            user_group = Group.objects.get(name=groups[0])
            user.groups.add(user_group)
        # Send activation email
        self._send_confirmation_mail(user)
        return user

    def _update_user(self, user, email, first_name, last_name, phone_number, groups):
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
        if phone_number:
            user.phone_number = phone_number
        if groups:
            if isinstance(groups, str):
                groups = [groups]
            user_group = Group.objects.get(name=groups[0])
            user.groups.clear()
            user.groups.add(user_group)
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
            recipient_list=[user.email],
        )
    def _bulk_create_users(self, users, groups):
        """
        Bulk create users from a request.
        Returns a list of created user objects.
        """
        if not users:
            raise ValidationError({'error': 'No user data provided'})
        created_users = []
        for user_data in users:
            user = self._create_user(
                email=user_data.get('email'),
                first_name=user_data.get('first_name'),
                last_name=user_data.get('last_name'),
                phone_number=user_data.get('phone_number', None),
                groups=groups
            )
            created_users.append(user)
        return created_users
        
class UserViewSet(AbstractUserViewSet):
    queryset = models.CustomUser.objects.all().order_by('id').prefetch_related('groups', 'student_profile')
    http_method_names = ['get', 'put', 'patch', 'delete', 'post']
    permission_classes = [core_permissions.IsInstructorOrAboveUser]


    def get_serializer_class(self):
        if self.request.method.lower() == 'post':
            return serializers.UserCreateSerializer
        return serializers.CustomUserSerializer

    @action(detail=False, methods=['get'], url_path='students')
    def students_list(self, request):
        group = Group.objects.get(name="student")
        data = self.queryset.filter(groups=group, is_active=True)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='instructors')
    def instructors_list(self, request):
        group = Group.objects.get(name="instructor")
        data = self.queryset.filter(groups=group, is_active=True)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    @action(detail=False, methods=['get'], url_path='branch-managers', permission_classes=[core_permissions.IsAdminUser])
    def instructors_list(self, request):
        group = Group.objects.get(name="branch-manager")
        is_available = request.query_params.get('available', None)
        is_available = is_available.lower() == 'true' if is_available else False
        data = self.queryset.filter(groups=group, is_active=True)
        if is_available:
            data = data.filter(branch__isnull=True)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='supervisors', permission_classes=[core_permissions.IsCoordinatorOrAboveUser])
    def supervisors_list(self, request):
        request_user = self.request.user
        request_user_groups = request_user.groups.values_list('name', flat=True)
        data = self.queryset.filter(groups__name="supervisor", is_active=True)
        if 'admin' in request_user_groups:
            serializer = self.get_serializer(data, many=True)
            return Response(serializer.data)
        if 'branch-manager' in request_user_groups:
            branch_of_request_user = request_user.branch
        if 'coordinator' in request_user_groups:
            branch_of_request_user = request_user.coordinator.branch
        data = data.filter(Q(tracks=None) | Q(tracks__default_branch=branch_of_request_user)).distinct()
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='admins')
    def admins_list(self, request):
        group = Group.objects.get(name="admin")
        data = self.queryset.filter(groups=group)
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], url_path='admins-and-supervisors')
    def admins_supervisors_list(self, request):
        group = Group.objects.filter(name__in=["admin", "supervisor", "branch-manager"])
        data = self.queryset.filter(groups__in=group).distinct()
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
    
    def create(self, request, *args, **kwargs):
        user = self._create_user(
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
            groups=kwargs.get('groups', request.data.get('groups', []))
        )
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    def update(self, request, *args, **kwargs):
        user = self._update_user(
            user=self.get_object(),
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
            groups=kwargs.get('groups', request.data.get('groups', []))
        )
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
            requestUserBranch = requestUser.branch
            return self.queryset.filter(coordinator__branch=requestUserBranch).order_by('id')
        return self.queryset.none()
    def create(self, request, *args, **kwargs):
        request_user = self.request.user
        request_user_branch = request_user.branch
        # Ensure the 'coordinator' group is included in kwargs
        groups = ['coordinator']
        user = self._create_user(
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
            groups=groups
        )
        coordinator = attend_models.Coordinator.objects.create(user=user, branch=request_user_branch)
        serializer = self.get_serializer(user)
        return Response({
            'user': serializer.data,
            'coordinator_id': coordinator.id
        }, status=status.HTTP_201_CREATED)
    def update(self, request, *args, **kwargs): #TODO add things to change in the coordinator profile
        user = self._update_user(
            user=self.get_object(),
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
        )
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
class GuestViewSet(AbstractUserViewSet):
    queryset = models.CustomUser.objects.filter(groups__name='guest').order_by('id')
    serializer_class = serializers.CustomUserSerializer
    permission_classes = [core_permissions.IsCoordinatorOrAboveUser] 

    def get_permissions(self):
        if self.action in ['create']:
            self.permission_classes = [] # Allow any one to create guest user
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        date_of_birth = request.data.get('date_of_birth')
        national_id = request.data.get('national_id')
        college_name = request.data.get('college_name')
        university_name = request.data.get('university_name')
        gradyear = request.data.get('gradyear')
        degree = request.data.get('degree')
        # Ensure the 'guest' group is included in kwargs
        groups = ['guest']
        user = self._create_user(
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
            groups=groups
        )
        # Create guest profile and associate with user
        guest_profile = attend_models.Guest.objects.create(
            user=user,
            date_of_birth=date_of_birth,
            national_id=national_id,
            college_name=college_name,
            university_name=university_name,
            gradyear=gradyear,
            degree_level=degree
        )
        serializer = self.get_serializer(user)
        return Response({'user': serializer.data, 'guest_profile': guest_profile.id}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request, *args, **kwargs):
        """
        Bulk create guests. Expects a list of user dicts in 'users'.
        Each user dict must include 'email', 'first_name', 'last_name', 'phone_number', and 'track_id'.
        """
        
        users = request.data.get('users', [])
        groups = ['guest']
        created_users = self._bulk_create_users(users, groups)

        guest_profiles = []
        for user in created_users:
            guest_profiles.append(attend_models.Guest(
                user=user,
                date_of_birth=request.data.get('date_of_birth'),
                national_id=request.data.get('national_id'),
                college_name=request.data.get('college_name'),
                university_name=request.data.get('university_name'),
                gradyear=request.data.get('gradyear'),
                degree_level=request.data.get('degree')
            ))
        attend_models.Guest.objects.bulk_create(guest_profiles)

        serializer = self.get_serializer(created_users, many=True)
        return Response({
            'message': 'Bulk guest user creation successful!',
            'users': serializer.data
            }, status=status.HTTP_201_CREATED)
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
            track = attend_models.Track.objects.get(id=trackParam) #TODO this might be a little too open
            students = students.filter(student_profile__track=track)
        if searchParam:
            students = students.filter(Q(email__icontains=searchParam) | Q(first_name__icontains=searchParam) | Q(last_name__icontains=searchParam)) # TODO consider adding capability for admins to view all students and add them
        if isactiveParam:
            isactiveParam = isactiveParam.lower() == 'true' if isactiveParam else False
            students = students.filter(student_profile__track__is_active=isactiveParam)
        if 'coordinator' in requestUserGroups:
            branch = attend_models.Branch.objects.get(coordinators=requestUser.coordinator)
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
        groups = request_user.groups.values_list('name', flat=True)

        # Get the track object from the body
        track_id = request.data.get('track_id')
        if not track_id:
            return Response({'error': 'Track ID is required'}, status=400)
        try:
            if 'supervisor' in groups:
                track_obj = request_user.tracks.get(id=track_id)
            elif 'coordinator' in groups:
                track_obj = attend_models.Track.objects.get(id=track_id, default_branch__coordinators=request_user.coordinator)
        except attend_models.Track.DoesNotExist:
            return Response({'error': "The requested track does not exist or you don't have authority over it."}, status=400)

        # Use AbstractUserViewSet's create to create the user and send email
        user = self._create_user(
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
            groups=['student']
        )

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
        user = self._update_user(
            user=self.get_object(),
            email=request.data.get('email'),
            first_name=request.data.get('first_name'),
            last_name=request.data.get('last_name'),
            phone_number=request.data.get('phone_number'),
        )
        serializer = self.get_serializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='make-inactive')
    def make_inactive(self, request, *args, **kwargs):
        student = self.get_object()
        student.is_active = False
        student.is_banned = True
        # delete attendance future records for user if they exist
        student_profile = student.student_profile
        upcoming_attendance_records =  student_profile.attendance_records.filter(schedule__created_at__gte=timezone.localtime())
        print(f"Deleting {upcoming_attendance_records.count()} attendance records for {student.email}.")
        upcoming_attendance_records.delete()
        return Response({'message': 'Student has been made inactive successfully.'})
    
    @action(detail=True, methods=['patch'], url_path='resend-activation')
    def resend_activation(self, request, *args, **kwargs):
        student = self.get_object()
        student.is_banned = False
        if student.is_active:
            return Response({'message': 'User is already active.'}, status=400)
        self._send_confirmation_mail(student)
        return Response({
            'confirmation_link': create_password_url
        })
    
    @action(detail=True, methods=['patch'], url_path='reset-uuid')
    def reset_uuid(self, request, *args, **kwargs):
        student = self.get_object()
        student.student_profile.phone_uuid = None
        student.student_profile.laptop_uuid = None
        student.student_profile.save()
        return Response({'message': 'UUID has been reset successfully.'})
    
    @action(detail=False, methods=['post'], url_path='bulk-create', permission_classes=[core_permissions.IsSupervisorOrAboveUser])
    def bulk_create(self, request, *args, **kwargs):
        """
        Bulk create students. Expects a list of user dicts in 'users'.
        Each user dict must include 'email', 'first_name', 'last_name', 'phone_number', and 'track_id'.
        """
        
        users = request.data.get('users', [])
        groups = ['student']
        created_users = self._bulk_create_users(users, groups)

        request_user = self.request.user
        request_user_groups = request_user.groups.values_list('name', flat=True)
        track_id = request.data.get('track_id')
        if not track_id:
            return Response({'error': 'Track ID is required for all users'}, status=400)
        try:
            if 'supervisor' in request_user_groups:
                track_obj = request_user.tracks.get(id=track_id)
            elif 'coordinator' in request_user_groups:
                track_obj = attend_models.Track.objects.get(id=track_id, default_branch__coordinators=request_user.coordinator)
        except:
            return Response({'error': f"The requested track does not exist or you don't have authority over it."}, status=400)
        student_profiles = []
        for user in created_users:
            student_profiles.append(attend_models.Student(
                track=track_obj,
                user=user
            ))
        attend_models.Student.objects.bulk_create(student_profiles)

        serializer = self.get_serializer(created_users, many=True)
        return Response({
            'message': 'Bulk student user creation successful!',
            'users': serializer.data
            }, status=status.HTTP_201_CREATED)

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

        password = get_random_string(length=8)
        user.set_password(password)
        user.save()
        if 'student' in user.groups.all().values_list('name', flat=True):
            student_profile = attend_models.Student.objects.get(user=user)
            # check for upcoming schedules and create attendance records for user if they don't exist
            upcoming_schedules = attend_models.Schedule.objects.filter(track=student_profile.track).exclude(sessions__end_time__lt=timezone.localtime()).distinct()
            numOfAttenCreated = 0
            for schedule in upcoming_schedules:
                record, created = attend_models.AttendanceRecord.objects.get_or_create(student=student_profile, schedule=schedule)
                if created:
                    numOfAttenCreated += 1
            print(f"Created {numOfAttenCreated} attendance records for {user.email}.")
            return Response({'message': 'User has been activated successfully.', 'attendance_records_created': numOfAttenCreated})
        send_mail(
            subject="Account Activation",
            message=f"Hi, {user.first_name},\nYour account has been activated.\nYour Email is: {user.email}\nYour new password is: {password}",
            from_email=os.environ.get('EMAIL_USER'),
            recipient_list=[user.email],
        )
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