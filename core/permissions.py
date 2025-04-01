from rest_framework.permissions import BasePermission
    
class BaseIsUserOrAbove(BasePermission):
    """
    Base user or above class that can be expanding by adding below
    """
    required_groups = []

    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=self.required_groups).exists() and request.user.is_active
class IsAdminUser(BaseIsUserOrAbove):
    """
    Check if user belongs to admin group.
    """
    required_groups = ['admin']
class IsSupervisorOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to supervisor group or below.
    """
    required_groups = ['admin', 'supervisor']
class IsInstructorOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to instructor group or above.
    """
    required_groups = ['admin', 'supervisor', 'instructor']
    
class IsStudentOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to student group or above.
    """
    required_groups = ['admin', 'supervisor', 'instructor', 'student']
    