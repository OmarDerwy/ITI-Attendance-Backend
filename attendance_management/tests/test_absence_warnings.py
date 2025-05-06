from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from ..models import Student, Track, Schedule, AttendanceRecord, PermissionRequest
from ..settings_models import ApplicationSetting
from users.models import CustomUser
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from ..serializers import AbsenceWarningSerializer
from django.urls import reverse

CustomUser = get_user_model()

class AbsenceWarningTests(TestCase):
    def setUp(self):
        # Create test users
        self.admin_user = CustomUser.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            groups=['admin']
        )
        self.student_user = CustomUser.objects.create_user(
            email='student@example.com',
            password='studentpass123',
            groups=['student']
        )
        
        # Create test track
        self.track = Track.objects.create(
            name='Test Track',
            supervisor=self.admin_user,
            intake=1,
            start_date=timezone.now().date(),
            description='Test Description'
        )
        
        # Create test student
        self.student = Student.objects.create(
            user=self.student_user,
            track=self.track
        )
        
        # Create test schedule
        self.schedule = Schedule.objects.create(
            track=self.track,
            name='Test Schedule',
            created_at=timezone.now().date()
        )
        
        # Set up API client
        self.client = APIClient()
        
        # Set initial thresholds
        ApplicationSetting.objects.create(
            key='unexcused_absence_threshold',
            value=2,
            description='Threshold for unexcused absences'
        )
        ApplicationSetting.objects.create(
            key='excused_absence_threshold',
            value=3,
            description='Threshold for excused absences'
        )

    def test_unexcused_absence_warning(self):
        """Test warning for unexcused absences"""
        # Create two unexcused absences
        for _ in range(2):
            AttendanceRecord.objects.create(
                student=self.student,
                schedule=self.schedule,
                check_in_time=None
            )
        
        # Check warning status
        has_warning, warning_type = self.student.has_exceeded_warning_threshold()
        self.assertTrue(has_warning)
        self.assertEqual(warning_type, 'unexcused')

    def test_excused_absence_warning(self):
        """Test warning for excused absences"""
        # Create three excused absences
        for _ in range(3):
            record = AttendanceRecord.objects.create(
                student=self.student,
                schedule=self.schedule,
                check_in_time=None
            )
            PermissionRequest.objects.create(
                student=self.student,
                schedule=self.schedule,
                request_type='day_excuse',
                status='approved',
                reason='Test excuse'
            )
        
        # Check warning status
        has_warning, warning_type = self.student.has_exceeded_warning_threshold()
        self.assertTrue(has_warning)
        self.assertEqual(warning_type, 'excused')

    def test_no_warning(self):
        """Test no warning when below thresholds"""
        # Create one unexcused absence
        AttendanceRecord.objects.create(
            student=self.student,
            schedule=self.schedule,
            check_in_time=None
        )
        
        # Create two excused absences
        for _ in range(2):
            record = AttendanceRecord.objects.create(
                student=self.student,
                schedule=self.schedule,
                check_in_time=None
            )
            PermissionRequest.objects.create(
                student=self.student,
                schedule=self.schedule,
                request_type='day_excuse',
                status='approved',
                reason='Test excuse'
            )
        
        # Check warning status
        has_warning, warning_type = self.student.has_exceeded_warning_threshold()
        self.assertFalse(has_warning)
        self.assertIsNone(warning_type)

    def test_update_thresholds(self):
        """Test updating absence thresholds"""
        # Login as admin
        self.client.force_authenticate(user=self.admin_user)
        
        # Update thresholds
        response = self.client.post('/api/settings/absence-thresholds/', {
            'unexcused_threshold': 4,
            'excused_threshold': 5
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unexcused_threshold'], 4)
        self.assertEqual(response.data['excused_threshold'], 5)
        
        # Verify in database
        unexcused_setting = ApplicationSetting.objects.get(key='unexcused_absence_threshold')
        excused_setting = ApplicationSetting.objects.get(key='excused_absence_threshold')
        self.assertEqual(unexcused_setting.value, 4)
        self.assertEqual(excused_setting.value, 5)

    def test_get_thresholds(self):
        """Test getting absence thresholds"""
        # Login as admin
        self.client.force_authenticate(user=self.admin_user)
        
        # Get thresholds
        response = self.client.get('/api/settings/absence-thresholds/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unexcused_threshold'], 2)
        self.assertEqual(response.data['excused_threshold'], 3) 