from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.pagination import PageNumberPagination
from ..models import Schedule, Track
from ..serializers import ScheduleSerializer
from core import permissions
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
        if 'supervisor' in groups:
            tracks = Track.objects.filter(supervisor=user)
            queryset = Schedule.objects.filter(track__in=tracks)
        elif 'admin' in groups:
            queryset = Schedule.objects.all()
        elif 'student' in groups:
            queryset = Schedule.objects.filter(track__students__user=user)
        else:
            queryset = Schedule.objects.none()

        track_id = self.request.query_params.get('track')
        if track_id:
            queryset = queryset.filter(track_id=track_id)

        return queryset