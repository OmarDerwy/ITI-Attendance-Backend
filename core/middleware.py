import os

# Set the Django settings module before initializing Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django
django.setup()  # Initialize Django apps

import jwt
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async

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
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope["headers"])
        auth_header = headers.get(b"authorization", b"").decode("utf-8")
        token = None

        # Extract the token from the "Authorization" header
        if auth_header.startswith("Bearer "):
            token = auth_header.split("Bearer ")[1]

        # Default to anonymous user
        scope["user"] = AnonymousUser()

        # If a token is provided, try to authenticate the user
        if token:
            scope["user"] = await get_user_from_token(token)

        return await self.inner(scope, receive, send)
