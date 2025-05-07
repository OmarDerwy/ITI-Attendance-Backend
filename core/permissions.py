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

class IsBranchManagerOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to branch-manager group or above.
    """
    required_groups = ['admin', 'branch-manager']

class IsCoordinatorOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to coordinator group or above.
    """
    required_groups = ['admin', 'branch-manager', 'coordinator']

class IsSupervisorOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to supervisor group or above.
    """
    required_groups = ['admin', 'branch-manager', 'coordinator', 'supervisor']

class IsInstructorOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to instructor group or above.
    """
    required_groups = ['admin', 'branch-manager', 'coordinator', 'supervisor', 'instructor']

class IsStudentOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to student group or above.
    """
    required_groups = ['admin', 'branch-manager', 'coordinator', 'supervisor', 'instructor', 'student']

class IsGuestOrAboveUser(BaseIsUserOrAbove):
    """
    Check if user belongs to guest group or above.
    """
    required_groups = ['admin', 'branch-manager', 'coordinator', 'supervisor', 'instructor', 'student', 'guest']
