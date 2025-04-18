from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from ..models import PermissionRequest, Schedule
from ..serializers import PermissionRequestSerializer
from core.permissions import IsSupervisorOrAboveUser, IsStudentOrAboveUser
from lost_and_found_system.utils import send_and_save_notification  # Import the notification function
from rest_framework import status

class PermissionRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing permission requests.
    Students can create requests, while supervisors or admins can view, approve, or reject them.
    """
    queryset = PermissionRequest.objects.select_related('student__user').all()  # Updated to use Student
    serializer_class = PermissionRequestSerializer

    def create(self, request, *args, **kwargs):

        request_type = request.data.get('request_type')
        adjusted_time = request.data.get('adjusted_time')
        reason = request.data.get('reason')
        schedule_id = request.data.get('schedule')

        # get schedule object
        if schedule_id:
            try:
                schedule = Schedule.objects.get(id=schedule_id)
            except Schedule.DoesNotExist:
                return Response({'error': 'Schedule not found'}, status=404)

        student = request.user.student_profile
        
        permission_request = PermissionRequest.objects.create(
            student=student,
            request_type=request_type,
            adjusted_time=adjusted_time,
            reason=reason,
            schedule=schedule,
        )

        # Send notification to the supervisor of the track
        supervisor = schedule.track.supervisor
        student_name = f"{student.user.first_name} {student.user.last_name}"
        request_type_display = dict(PermissionRequest.REQUEST_TYPES).get(request_type, request_type)
        
        notification_message = (
            f"{student_name} has submitted a new {request_type_display} request for "
            f"{schedule.name} on {schedule.created_at.strftime('%d %b, %Y')}. "
            f"Reason: {reason}"
        )
        
        send_and_save_notification(
            user=supervisor,
            title="New Permission Request",
            message=notification_message
        )

        permission_request.save()
        return Response({
            'message': 'Request created successfully',
            'object': self.get_serializer(permission_request).data,
            'data': request.data,
        })

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
            return self.queryset.filter(student__track__supervisor=user).filter(status='pending')
        return self.queryset.filter(student__user=user)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """
        Approve a permission request.
        Only supervisors or admins can perform this action.
        """
        permission_request = self.get_object()

        adjusted_time = request.data.get('adjusted_time')
        permission_request.adjusted_time = adjusted_time
        permission_request.status = 'approved'
        permission_request.save()
        
        # Send notification to the student that their request was approved
        student = permission_request.student
        schedule = permission_request.schedule
        request_type_display = dict(PermissionRequest.REQUEST_TYPES).get(permission_request.request_type, permission_request.request_type)
        
        notification_message = (
            f"Your {request_type_display} request for {schedule.name} on "
            f"{schedule.created_at.strftime('%d %b, %Y')} has been approved. "
            f"Adjusted time: {permission_request.adjusted_time.strftime('%H:%M') if permission_request.adjusted_time else 'N/A'}"
        )
        
        send_and_save_notification(
            user=student.user,
            title="Permission Request Approved",
            message=notification_message
        )
        
        return Response({
            'message': 'Request approved successfully',
            'object': self.get_serializer(permission_request).data,
            'data': request.data,
        })

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """
        Reject a permission request.
        Only supervisors or admins can perform this action.
        """
        permission_request = self.get_object()
        permission_request.status = 'rejected'
        permission_request.save()
        
        # Send notification to the student that their request was rejected
        student = permission_request.student
        schedule = permission_request.schedule
        request_type_display = dict(PermissionRequest.REQUEST_TYPES).get(permission_request.request_type, permission_request.request_type)
        
        notification_message = (
            f"Your {request_type_display} request for {schedule.name} on "
            f"{schedule.created_at.strftime('%d %b, %Y')} has been rejected. "
            f"Please contact your supervisor for more information."
        )
        
        send_and_save_notification(
            user=student.user,
            title="Permission Request Rejected",
            message=notification_message
        )
        
        return Response({'message': 'Request rejected successfully'}, status=status.HTTP_200_OK)
