from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from ..models import PermissionRequest
from ..serializers import PermissionRequestSerializer
from core.permissions import IsSupervisorOrAboveUser, IsStudentOrAboveUser

class PermissionRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing permission requests.
    Students can create requests, while supervisors or admins can view, approve, or reject them.
    """
    queryset = PermissionRequest.objects.select_related('student__user').all()
    serializer_class = PermissionRequestSerializer

    def get_permissions(self):
        """
        Assign permissions based on the action.
        Supervisors or admins can list, approve, or reject requests.
        Students can create or view their own requests.
        """
        if self.action in ['list', 'approve', 'reject']:
            return [IsSupervisorOrAboveUser()]
        return [IsStudentOrAboveUser()]

    def get_queryset(self):
        """
        Filter the queryset based on the user's role.
        Supervisors see requests for students in their track.
        Students see only their own requests.
        """
        user = self.request.user
        if user.groups.filter(name='supervisor').exists():
            return self.queryset.filter(student__track__supervisor=user)
        return self.queryset.filter(student__user=user)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        Approve a permission request.
        Only supervisors or admins can perform this action.
        """
        permission_request = self.get_object()
        permission_request.status = 'approved'
        permission_request.save()
        return Response({'message': 'Request approved successfully'})

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """
        Reject a permission request.
        Only supervisors or admins can perform this action.
        """
        permission_request = self.get_object()
        permission_request.status = 'rejected'
        permission_request.save()
        return Response({'message': 'Request rejected successfully'})
