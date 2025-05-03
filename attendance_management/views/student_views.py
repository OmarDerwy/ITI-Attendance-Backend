from rest_framework import viewsets, status
from ..models import Student, Schedule
from ..serializers import StudentSerializer, StudentWithWarningSerializer
from core import permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from django.db.models import Count, Subquery, OuterRef, Q
from ..models import PermissionRequest, ApplicationSetting, Track


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()  # Updated to use Student
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]  # CHECK if too much permissions to student


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
        Get students who have exceeded absence thresholds.
        """
        from django.utils import timezone

        thresholds = {
            'nine_months': {
                'excused': ApplicationSetting.get_excused_absence_threshold('nine_months'),
                'unexcused': ApplicationSetting.get_unexcused_absence_threshold('nine_months')
            },
            'intensive': {
                'excused': ApplicationSetting.get_excused_absence_threshold('intensive'),
                'unexcused': ApplicationSetting.get_unexcused_absence_threshold('intensive')
            }
        }

        # Get only past schedules
        today = timezone.now().date()
        past_schedules = Schedule.objects.filter(created_at__lt=today)

        # Get approved excuses
        approved_excuses = PermissionRequest.objects.filter(
            student=OuterRef('pk'),
            request_type='day_excuse',
            status='approved',
            schedule__in=past_schedules
        ).values('schedule_id')

        tracks = Track.objects.filter(supervisor=request.user)

        # Get students with absences
        students = Student.objects.select_related('user', 'track').filter(
            track__in=tracks,
            attendance_records__check_in_time__isnull=True,  # Has at least one absence
            attendance_records__schedule__in=past_schedules
        ).distinct().annotate(
            unexcused_count=Count('attendance_records', filter=Q(
                attendance_records__check_in_time__isnull=True,
                attendance_records__schedule__in=past_schedules
            ) & ~Q(
                attendance_records__schedule_id__in=Subquery(approved_excuses)
            )),
            excused_count=Count('attendance_records', filter=Q(
                attendance_records__check_in_time__isnull=True,
                attendance_records__schedule__in=past_schedules,
                attendance_records__schedule_id__in=Subquery(approved_excuses)
            ))
        )

        # Filter students who exceed thresholds
        students_with_warnings = []
        for student in students:
            program_type = student.track.program_type
            if (student.unexcused_count >= thresholds[program_type]['unexcused'] or
                student.excused_count >= thresholds[program_type]['excused']):
                students_with_warnings.append(student)

        serializer = StudentWithWarningSerializer(students_with_warnings, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)