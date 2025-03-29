from rest_framework import viewsets
from ..models import Track
from ..serializers import TrackSerializer
from core.permissions import IsSupervisorUser

class TrackViewSet(viewsets.ModelViewSet):
    queryset = Track.objects.select_related('supervisor', 'branch').all()
    serializer_class = TrackSerializer
    permission_classes = [IsSupervisorUser] # TODO change into new permissions system
