from rest_framework import viewsets
from ..models import Branch
from ..serializers import BranchSerializer
from core import permissions

class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all().order_by('id')
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsSupervisorOrAboveUser]
    pagination_class = None 

    def get_queryset(self):
        user = self.request.user
        groups = user.groups.values_list('name', flat=True)
        queryset = self.queryset
        print(queryset)

        if 'coordinator' in groups:
            # Get the branch where the user is the coordinator
            return queryset.filter(coordinators__user=user)
        elif 'admin' in groups:
            # Admin can see all branches
            return queryset
        else:
            return Branch.objects.none()