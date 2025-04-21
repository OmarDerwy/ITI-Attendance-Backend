from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.pagination import PageNumberPagination
from django.db.models import Prefetch
from ..models import Schedule, Track, Student, AttendanceRecord, PermissionRequest, Session
from ..serializers import ScheduleSerializer
from core import permissions
from attendance_management.models import ApplicationSetting

# Add custom pagination class
class CustomPagination(PageNumberPagination):
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for key in ['next', 'previous']:
            link = response.data.get(key)
            if link:
                response.data[key] = link.replace("http://localhost:8000/api/v1/", "")
        return response

class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]
    pagination_class = CustomPagination  # added custom pagination

    def get_queryset(self):
        user = self.request.user
        groups = user.groups.values_list('name', flat=True)
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        track_id = self.request.query_params.get('track')

        if 'supervisor' in groups:
            tracks = Track.objects.filter(supervisor=user)
            queryset = Schedule.objects.filter(track__in=tracks)
        elif 'admin' in groups:
            queryset = Schedule.objects.all()
        elif 'student' in groups:
            queryset = Schedule.objects.filter(track__students__user=user)
        else:
            queryset = Schedule.objects.none()
        # query for track_id
        if track_id:
            queryset = queryset.filter(track_id=track_id)
        # query for date range
        if from_date and to_date:
            queryset = queryset.filter(created_at__range=[from_date, to_date])
        elif from_date:
            queryset = queryset.filter(created_at=from_date)

        # Optimize related fetching for serializer fields only on 'retrieve' action
        if getattr(self, 'action', None) == 'retrieve':
            queryset = queryset.select_related(
            'track',
            'custom_branch',
            ).prefetch_related(
            Prefetch('sessions', queryset=Session.objects.select_related('schedule', 'track')),
            Prefetch('attendance_records', queryset=AttendanceRecord.objects.select_related('student', 'student__user', 'student__track', 'schedule')),
            # Prefetch students and their attendance_records and permission_requests for absence calculations
            Prefetch(
                'track__students',
                queryset=Student.objects.select_related('user', 'track')
                .prefetch_related(
                    Prefetch(
                    'attendance_records',
                    queryset=AttendanceRecord.objects.select_related('schedule')
                    ),
                    Prefetch(
                    'permission_requests',
                    queryset=PermissionRequest.objects.select_related('schedule')
                    ),
                )
            ),
            'track__students__user__groups',
            )
        else:
            queryset = queryset.select_related(
                'track'
            ).prefetch_related(
                'sessions',
            )

        queryset = queryset.order_by('-created_at')
        return queryset

    def list(self, request, *args, **kwargs):
        user = request.user
        groups = user.groups.values_list('name', flat=True)
        if 'student' in groups:
            self.pagination_class = None  # Disable pagination for students
        # Prefetch all ApplicationSetting objects and cache them for this request
        settings_qs = ApplicationSetting.objects.all()
        settings_map = {s.key: s for s in settings_qs}
        # Attach to request for use in serializers/models
        request._application_settings_map = settings_map
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        # Prefetch all ApplicationSetting objects and cache them for this request
        settings_qs = ApplicationSetting.objects.all()
        settings_map = {s.key: s for s in settings_qs}
        request._application_settings_map = settings_map
        return super().retrieve(request, *args, **kwargs)
