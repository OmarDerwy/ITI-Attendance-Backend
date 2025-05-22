from rest_framework import viewsets
from ..models import Branch
from ..serializers import BranchSerializer
from core import permissions
from rest_framework.decorators import action
from rest_framework.response import Response

class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all().order_by('id')
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsSupervisorOrAboveUser]
    pagination_class = None 

    @action(detail=False, methods=['get'], url_path='own-branch')
    def get_own_branch(self, request):
        """
        Get the branch of the logged-in user.
        """
        user = request.user
        if hasattr(user, 'branch'):
            branch = user.branch
            branch = [branch]
            serializer = self.get_serializer(branch, many=True)
            return Response(serializer.data)
        elif hasattr(user, 'coordinator'):
            # If the user is a coordinator, get the branch through the coordinator
            branch = user.coordinator.branch
            branch = [branch]
            serializer = self.get_serializer(branch, many=True)
            return Response(serializer.data)
        else:
            all_branches = self.queryset
            serializer = self.get_serializer(all_branches, many=True)
            return Response(serializer.data)