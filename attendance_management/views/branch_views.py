from rest_framework import viewsets
from ..models import Branch
from ..serializers import BranchSerializer
from core import permissions
from users.models import CustomUser

class BranchViewSet(viewsets.ModelViewSet):
    # def get_queryset(self):
    #     user: CustomUser = self.request.user
    #     user_groups = user.groups.all().values_list('name', flat=True)
    #     if 'admin' in user_groups:
    #         return Branch.objects.all()
    #     if 'supervisor' in user_groups:
    #         branches = Branch.objects.all()
    #         branches = branches.tracks_set(supervisor=user)
    #     if 'student' in user_groups:
    #         branches = Branch.objects.all()
    #         branches = branches.tracks_set() # TODO continue this logic
    #         return 
    #     return super().get_queryset()
    

    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if student has too much permissions
