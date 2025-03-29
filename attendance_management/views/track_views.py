from rest_framework import viewsets
from ..models import Track
from ..serializers import TrackSerializer
from core import permissions

class TrackViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        user = self.request.user
        user_groups = user.groups.values_list('name', flat=True)
        if 'admin' in user_groups:
            return Track.objects.all()
        return Track.objects.select_related('supervisor', 'branch').all()
    
    def get_permissions(self):
        if self.action == 'list':
            return [permissions.IsStudentOrAboveUser(), ]
        return [permissions.IsSupervisorOrAboveUser(), ]
    
    serializer_class = TrackSerializer