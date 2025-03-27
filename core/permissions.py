from rest_framework.permissions import BasePermission
# class IsSupervisorUser(BasePermission):
#     def has_permission(self, request, view):
#         group = Group.objects.get(name='supervisor')
#         return bool(request.user and request.user in group.user_set.all())
    
# class IsInstructorUser(BasePermission):
#     def has_permission(self, request, view):
#         group = Group.objects.get(name='instructor')
#         return bool(request.user and request.user in group.user_set.all())

# class IsStudentUser(BasePermission):
#     def has_permission(self, request, view):
#         group = Group.objects.get(name='student')
#         return bool(request.user and request.user in group.user_set.all())

class HasRequiredGroupForView(BasePermission):
    """
    Check if user belongs to required groups defined on the view.
    """
    def has_permission(self, request, view):
        required_groups = getattr(view, 'required_groups', [])
        
        if not required_groups:
            return True  # No group requirements
            
        if isinstance(required_groups, str):
            required_groups = [required_groups]
            
        required_groups = [group.lower() for group in required_groups]
        user_groups = request.user.groups.values_list('name', flat=True)
        return bool(set(required_groups).intersection(set(user_groups)))