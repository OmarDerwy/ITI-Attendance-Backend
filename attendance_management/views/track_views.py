from rest_framework import viewsets
from ..models import Track
from ..serializers import TrackSerializer
from core import permissions

class TrackViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsSupervisorOrAboveUser]
    def get_queryset(self):
        user = self.request.user
        user_groups = user.groups.values_list('name', flat=True)
        queryset = Track.objects.select_related('default_branch', 'supervisor')
        program_type = self.request.query_params.get('program_type')
        is_active = self.request.query_params.get('is_active')
        if program_type:
            queryset = queryset.filter(program_type=program_type)
        if is_active:
            is_active = is_active.lower() == 'true' if is_active else False
            queryset = queryset.filter(is_active=is_active)
        if 'admin' in user_groups:
            return queryset
        if 'coordinator' in user_groups:
            return queryset.filter(default_branch__coordinators=user)
        if 'supervisor' in user_groups:
            return queryset.filter(supervisor=user)
        return Track.objects.none()  # No access for other users

    
    serializer_class = TrackSerializer
    pagination_class = None 