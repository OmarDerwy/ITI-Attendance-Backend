from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now

from ..models import Schedule
from ..serializers import ScheduleSerializer
from core import permissions

class ScheduleViewSet(viewsets.ModelViewSet):
    queryset = Schedule.objects.all()
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if too much permission to student

    # @action(detail=False, methods=['get'], url_path='search')
    # def search(self, request):
    #     """
    #     Allow users to search schedules based on a time period (day, week, month)
    #     and/or filter schedules by track.
    #     """
    #     period = request.query_params.get('period', None)
    #     track_id = request.query_params.get('track_id')
    #     track_name = request.query_params.get('track_name')
    #     today = now().date()

    #     # Filter by period
    #     if period == 'day':
    #         schedules = self.queryset.filter(sessions__start_time__date=today)
    #     elif period == 'week':
    #         start_of_week = today - timedelta(days=today.weekday())
    #         end_of_week = start_of_week + timedelta(days=6)
    #         schedules = self.queryset.filter(sessions__start_time__date__range=[start_of_week, end_of_week])
    #     elif period == 'month':
    #         schedules = self.queryset.filter(sessions__start_time__month=today.month)
    #     elif period is None:
    #         schedules = self.queryset  # No period filter applied
    #     else:
    #         return Response({'error': 'Invalid period'}, status=400)

    #     # Filter by track
    #     if track_id:
    #         schedules = schedules.filter(track__id=track_id)
    #     elif track_name:
    #         schedules = schedules.filter(track__name__icontains=track_name)

    #     serializer = self.get_serializer(schedules, many=True)
    #     return Response(serializer.data)
# 
