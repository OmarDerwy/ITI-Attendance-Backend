from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from core.helpers import verify_clerk_jwt

class ClerkUser:
    """
    A custom user-like object to wrap the decoded Clerk JWT token.
    """
    def __init__(self, decoded_token):
        self.decoded_token = decoded_token

    @property
    def is_authenticated(self):
        return True  # All verified tokens are considered authenticated

    def __getattr__(self, name):
        # Allow access to decoded token fields as attributes
        return self.decoded_token.get(name, None)


class ClerkJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None  # No token provided

        token = auth_header.split(" ")[1]
        try:
            # Verify the JWT token
            decoded_token = verify_clerk_jwt(token)
            return (ClerkUser(decoded_token), None)  # Return a ClerkUser object
        except Exception as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")