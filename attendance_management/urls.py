from django.urls import path, include
from rest_framework.routers import DefaultRouter
from attendance_management.views.branch_views import BranchViewSet
from attendance_management.views.schedule_views import ScheduleViewSet
from attendance_management.views.session_views import SessionViewSet
from attendance_management.views.student_views import StudentViewSet
from attendance_management.views.track_views import TrackViewSet
router = DefaultRouter()
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'tracks', TrackViewSet, basename='track')
router.register(r'branches', BranchViewSet, basename='branch')

urlpatterns = [
    path('', include(router.urls)),
]
