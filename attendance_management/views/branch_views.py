from rest_framework import viewsets
from ..models import Branch
from ..serializers import BranchSerializer
from core.permissions import IsSupervisorUser

class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsSupervisorUser] #make admin
