from rest_framework import viewsets, status
from ..models import Student
from ..serializers import StudentSerializer, StudentWithWarningSerializer
from core import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from django.db.models import Prefetch
from django.db.models import Count, Q, F
from ..models import PermissionRequest, ApplicationSetting

class CustomPagination(PageNumberPagination):
    page_size = 10  # 10 students per page
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for key in ['next', 'previous']:
            link = response.data.get(key)
            if link:
                response.data[key] = link.replace("http://localhost:8000/api/v1/", "") # TODO change this as soon as possible
        return response

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()  # Updated to use Student
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]  # CHECK if too much permissions to student
    pagination_class = CustomPagination  # added custom pagination

    # url to call this action is 
    @action(detail=False, methods=['get'], url_path='by-user-id')
    def get_student_by_user_id(self, request):
        """
        Retrieve a student with their track details by userId.
        """
        user_id = request.query_params.get('userId')
        if not user_id:
            return Response({'error': 'userId query parameter is required.'}, status=400)

        try:
            student = Student.objects.select_related('track', 'track__default_branch').get(user_id=user_id)
        except Student.DoesNotExist:
            raise NotFound({'error': 'No student found for the given userId.'})

        data = {
            'id': student.id,
            'phone_uuid': student.phone_uuid,
            'track': {
                'id': student.track.id,
                'name': student.track.name,
                'description': student.track.description,
                'program_type': student.track.program_type,
                'intake': student.track.intake,
                'start_date': student.track.start_date,
            },
            'branch': {
                'id': student.track.default_branch.id,
                'name': student.track.default_branch.name,
                'location_url': student.track.default_branch.location_url,
                'latitude': student.track.default_branch.latitude,
                'longitude': student.track.default_branch.longitude,
                'radius': student.track.default_branch.radius,
            },
        }
        return Response(data, status=200)

    @action(detail=False, methods=['get'], url_path='with-warnings', permission_classes=[permissions.IsSupervisorOrAboveUser])
    def students_with_warnings(self, request):
        """
        Retrieve a list of students who have exceeded either the excused or unexcused absence threshold.
        Optimized by using database queries to filter students with warnings.
        Only accessible by Supervisors and Admins.
        """
        # Get all students with their related data
        students = Student.objects.select_related('user', 'track').prefetch_related(
            'attendance_records',
            'permission_requests'
        )

        # Get thresholds for both program types
        nine_months_unexcused = ApplicationSetting.get_unexcused_absence_threshold('nine_months')
        nine_months_excused = ApplicationSetting.get_excused_absence_threshold('nine_months')
        intensive_unexcused = ApplicationSetting.get_unexcused_absence_threshold('intensive')
        intensive_excused = ApplicationSetting.get_excused_absence_threshold('intensive')

        # Filter students with warnings using database queries
        students_with_warnings = []
        for student in students:
            # Get the appropriate thresholds based on program type
            unexcused_threshold = nine_months_unexcused if student.track.program_type == 'nine_months' else intensive_unexcused
            excused_threshold = nine_months_excused if student.track.program_type == 'nine_months' else intensive_excused

            # Count unexcused absences (no check-in and no approved excuse)
            unexcused_count = student.attendance_records.filter(
                check_in_time__isnull=True
            ).exclude(
                schedule_id__in=PermissionRequest.objects.filter(
                    student=student,
                    request_type='day_excuse',
                    status='approved'
                ).values_list('schedule_id', flat=True)
            ).count()

            # Count excused absences (no check-in but has approved excuse)
            excused_count = student.attendance_records.filter(
                check_in_time__isnull=True,
                schedule_id__in=PermissionRequest.objects.filter(
                    student=student,
                    request_type='day_excuse',
                    status='approved'
                ).values_list('schedule_id', flat=True)
            ).count()

            # Check if student has exceeded either threshold
            if unexcused_count >= unexcused_threshold or excused_count >= excused_threshold:
                students_with_warnings.append(student)

        # Serialize the filtered list
        serializer = StudentWithWarningSerializer(students_with_warnings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


