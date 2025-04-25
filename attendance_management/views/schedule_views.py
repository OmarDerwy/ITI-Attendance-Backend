from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now
from rest_framework.pagination import PageNumberPagination
from ..models import Schedule, Track
from ..serializers import ScheduleSerializer
from core import permissions
import os
from dotenv import load_dotenv

# Load environment variables
API_BASE_URL = os.environ.get('API_BASE_URL')

# Add custom pagination class
class CustomPagination(PageNumberPagination):
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for key in ['next', 'previous']:
            link = response.data.get(key)
            if link:
                response.data[key] = link.replace(API_BASE_URL, "")
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
        # order by created_at descending
        queryset = queryset.order_by('-created_at')
        return queryset

    def list(self, request, *args, **kwargs):
        user = request.user
        groups = user.groups.values_list('name', flat=True)
        if 'student' in groups:
            self.pagination_class = None  # Disable pagination for students
        return super().list(request, *args, **kwargs)
