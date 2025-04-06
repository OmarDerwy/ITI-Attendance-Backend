from rest_framework import viewsets
from ..models import Branch
from ..serializers import BranchSerializer
from core import permissions
from users.models import CustomUser

class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsSupervisorOrAboveUser]
