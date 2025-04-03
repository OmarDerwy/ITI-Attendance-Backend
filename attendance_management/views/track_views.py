from rest_framework import viewsets
from ..models import Track
from ..serializers import TrackSerializer
from core import permissions

class TrackViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        user = self.request.user
        user_groups = user.groups.values_list('name', flat=True)
        queryset = Track.objects.select_related('default_branch', 'supervisor')
        program_type = self.request.query_params.get('program_type')
        if program_type:
            queryset = queryset.filter(program_type=program_type)
        if 'admin' in user_groups:
            return queryset
        return queryset.all()
    
    def get_permissions(self):
        return [permissions.IsAdminUser(), ]
    
    serializer_class = TrackSerializer