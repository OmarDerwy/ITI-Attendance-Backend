from django.urls import path, include
from rest_framework import routers
from .viewsets import UserViewSet, GroupViewSet, ResetPassword, UserActivateView, StudentViewSet, CoordinatorViewSet, GuestViewSet, ResetPasswordConfirmation, TokenBlacklistViewAll
from rest_framework_simplejwt.views import TokenBlacklistView

# from .views import bulk_create_users
router = routers.DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'users', UserViewSet, basename='user')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'coordinators', CoordinatorViewSet, basename='coordinator')
router.register(r'guests', GuestViewSet, basename='guest')

urlpatterns = [
    path('', include(router.urls), name='user-list'),
    path('auth/', include('djoser.urls.jwt'), name='auth-jwt'),
    path('auth/', include('djoser.urls'), name='auth'),
    path ('reset/', ResetPassword.as_view(), name='reset'),
    path ('reset-confirmation/', ResetPasswordConfirmation.as_view(), name='reset-confirmation'),
    path('activate/', UserActivateView.as_view(), name='activate-user'),
    path('auth/jwt/blacklist/', TokenBlacklistView.as_view(), name='token-blacklist'),
    path('auth/jwt/blacklist/all/', TokenBlacklistViewAll.as_view(), name='token-blacklist-all'),

    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'), name='rest_framework'),
    # path('auth/', include('djoser.urls.authtoken'), name='auth-token'),
    # # Authentication endpoints
    # path('register/', UserViewSet.as_view(), name='user-register'),
    # path('login/', LoginView.as_view(), name='user-login'),
    
    # Password management
    # path('password/reset/', PasswordResetView.as_view(), name='password-reset'),
    # path('password/reset/confirm/<str:uidb64>/<str:token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]