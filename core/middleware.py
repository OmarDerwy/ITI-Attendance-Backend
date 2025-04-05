import os

# Set the Django settings module before initializing Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()  # Initialize Django apps

import jwt
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async
from urllib.parse import parse_qs

@database_sync_to_async
def get_user_from_token(token):
    """
    Fetch the user from the database using the JWT token.
    """
    from users.models import CustomUser  # Import models here to avoid premature access
    try:
        validated_token = AccessToken(token)
        user_id = validated_token["user_id"]
        return CustomUser.objects.get(id=user_id)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, CustomUser.DoesNotExist, KeyError):
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    Custom middleware to authenticate WebSocket connections using JWT.
    Token can be provided either as a query parameter 'token=' or in the Authorization header.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Default to anonymous user
        scope["user"] = AnonymousUser()
        
        # Try to get token from query string first
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = None
        
        if "token" in query_params:
            # Extract token from query parameter
            token = query_params["token"][0]
        else:
            # If not in query params, try the Authorization header
            headers = dict(scope["headers"])
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            
            if auth_header.startswith("Bearer "):
                token = auth_header.split("Bearer ")[1]

        # If a token is provided, try to authenticate the user
        if token:
            scope["user"] = await get_user_from_token(token)

        return await self.inner(scope, receive, send)
