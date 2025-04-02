from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views.branch_views import BranchViewSet
from attendance_management.views.schedule_views import ScheduleViewSet
from attendance_management.views.session_views import SessionViewSet
from attendance_management.views.student_views import StudentViewSet
from attendance_management.views.track_views import TrackViewSet
from attendance_management.views.permission_request_views import PermissionRequestViewSet
from attendance_management.views.attendance_views  import AttendanceViewSet

router = DefaultRouter()
router.register(r'schedules', ScheduleViewSet, basename='schedule')
router.register(r'sessions', SessionViewSet, basename='session')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'tracks', TrackViewSet, basename='track')
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'permission-requests', PermissionRequestViewSet, basename='permissionrequest')
router.register(r'', AttendanceViewSet, basename='attendance')  # Register with empty prefixrouter.register(r'attendance', AttendanceViewSet, basename='attendance')

urlpatterns = [
    path('', include(router.urls)),
]
