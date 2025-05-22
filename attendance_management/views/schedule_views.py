from rest_framework import viewsets
from ..models import Schedule, Track
from ..serializers import ScheduleSerializer
from core import permissions



class ScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ScheduleSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]

    def get_queryset(self):
        user = self.request.user
        queryset = Schedule.objects.all().filter(event=None)
        groups = user.groups.values_list('name', flat=True)
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        track_id = self.request.query_params.get('track')

        if 'coordinator' in groups:
            # Get the branch where the user is the coordinator
            branch = user.coordinator.branch
            tracks = Track.objects.filter(default_branch=branch)
            queryset.filter(track__in=tracks)
        elif 'supervisor' in groups:
            tracks = Track.objects.filter(supervisor=user)
            queryset.filter(track__in=tracks)
        elif 'admin' in groups:
            queryset.all()
        elif 'student' in groups:
            queryset.filter(track__students__user=user)
        else:
            return Schedule.objects.none()  # No access for other users
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
