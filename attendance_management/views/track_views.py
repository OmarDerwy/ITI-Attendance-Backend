from rest_framework import viewsets
from ..models import Track
from ..serializers import TrackSerializer
from core import permissions
from rest_framework.decorators import action


class TrackViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsSupervisorOrAboveUser]
    serializer_class = TrackSerializer
    pagination_class = None 

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
            coordinator_profile = user.coordinator
            return queryset.filter(default_branch__coordinators=coordinator_profile)
        if 'supervisor' in user_groups:
            return queryset.filter(supervisor=user)
        return Track.objects.none()  # No access for other users
    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsSupervisorOrAboveUser])
    def archive_track(self, request, pk=None):
        """
        Archive a track.
        """
        track = self.get_object()
        track.is_active = False
        track.save()
        return Response({'status': 'Track archived successfully.'}, status=200)