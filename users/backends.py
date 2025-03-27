from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

User = get_user_model()

class ClerkAuthBackend(BaseBackend):
    def authenticate(self, request, clerk_user_id=None):
        if not clerk_user_id:
            return None
        try:
            user = User.objects.get(clerk_user_id=clerk_user_id)
            return user
        except ObjectDoesNotExist:
            # Optionally create a new user here if auto-creation is desired
            # user = User.objects.create_user(username=f"clerk_user_{clerk_user_id}", clerk_user_id=clerk_user_id)
            return None  # Or return None if auto-creation is not desired

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None