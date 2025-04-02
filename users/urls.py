from django.urls import path, include
from rest_framework import routers
from .viewsets import UserViewSet, GroupViewSet, ResetPassword, BulkCreateStudents, UserActivateView, StudentViewSet
# from .views import bulk_create_users
router = routers.DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')
router.register(r'users', UserViewSet, basename='user')
router.register(r'students', StudentViewSet, basename='student')

urlpatterns = [
    path('', include(router.urls), name='user-list'),
    path('auth/', include('djoser.urls.jwt'), name='auth-jwt'),
    path('auth/', include('djoser.urls'), name='auth'),
    path ('reset/', ResetPassword.as_view(), name='reset'),
    path('bulkcreate/', BulkCreateStudents.as_view(), name='bulk-create-users'),
    path('activate/', UserActivateView.as_view(), name='activate-user'),

    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'), name='rest_framework'),
    # path('auth/', include('djoser.urls.authtoken'), name='auth-token'),
    # # Authentication endpoints
    # path('register/', UserViewSet.as_view(), name='user-register'),
    # path('login/', LoginView.as_view(), name='user-login'),
    
    # Password management
    # path('password/reset/', PasswordResetView.as_view(), name='password-reset'),
    # path('password/reset/confirm/<str:uidb64>/<str:token>/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
]