from django.urls import path, include
from rest_framework import routers
from .viewsets import UserViewSet

router = routers.DefaultRouter()
router.register(r'', UserViewSet, basename='user')

urlpatterns = [
    path('', include(router.urls), name='user-list'),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework'), name='rest_framework'),
    
    # path('auth/', include('djoser.urls.authtoken'), name='auth-token'),
    # # Authentication endpoints
    # path('register/', UserViewSet.as_view(), name='user-register'),
    # path('login/', LoginView.as_view(), name='user-login'),
    
    # Password management
    # path('password/reset/', PasswordResetView.as_view(), name='password-reset'),
    # path('password/reset/confirm/<str:uidb64>/<str:token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]