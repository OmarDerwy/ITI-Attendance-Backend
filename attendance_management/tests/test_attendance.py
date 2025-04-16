from django.test import TestCase
from django.contrib.auth import get_user_model
from ..models import Track, Student, Schedule, AttendanceRecord, Branch, Session
from rest_framework.test import APIClient
from django.urls import reverse
from datetime import datetime, timedelta
from django.utils import timezone

CustomUser = get_user_model()

class AttendanceTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create admin user
        self.admin_user = CustomUser.objects.create_user(
            email='admin@example.com',
            password='adminpass123',
            groups=['admin']
        )
        
        # Create student user
        self.student_user = CustomUser.objects.create_user(
            email='student@example.com',
            password='studentpass123',
            first_name='John',
            last_name='Doe',
            groups=['student']
        )

        # Create branch
        self.branch = Branch.objects.create(
            name="Smart Village Branch",
            latitude=30.0722,
            longitude=31.0177,
            radius=100
        )

        # Create track with all required fields
        self.track = Track.objects.create(
            name="Computer Science",
            intake=1,
            supervisor=self.admin_user,
            start_date=timezone.now().date(),
            description="Test track for attendance",
            default_branch=self.branch
        )

        # Create student
        self.student = Student.objects.create(
            user=self.student_user,
            track=self.track
        )

        # Create schedule
        self.schedule = Schedule.objects.create(
            name="Test Schedule",
            track=self.track,
            custom_branch=self.branch,
            created_at=timezone.now()
        )

        # Create sessions for the schedule
        self.session1 = Session.objects.create(
            schedule=self.schedule,
            track=self.track,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2)
        )

        self.session2 = Session.objects.create(
            schedule=self.schedule,
            track=self.track,
            start_time=timezone.now() + timedelta(hours=2),
            end_time=timezone.now() + timedelta(hours=4)
        )

        # Create attendance record
        self.attendance = AttendanceRecord.objects.create(
            student=self.student,
            schedule=self.schedule
        )

    def test_attendance_creation(self):
        self.assertEqual(self.attendance.student, self.student)
        self.assertEqual(self.attendance.schedule, self.schedule)
        # Don't expect check_in_time to be set initially
        self.assertIsNone(self.attendance.check_in_time)

    def test_attendance_update(self):
        new_time = timezone.now() + timedelta(hours=1)
        self.attendance.check_out_time = new_time
        self.attendance.save()
        self.assertEqual(self.attendance.check_out_time, new_time)

    def test_attendance_deletion(self):
        self.attendance.delete()
        self.assertEqual(AttendanceRecord.objects.count(), 0)

    def test_check_in(self):
        self.client.force_authenticate(user=self.student_user)
        # Use coordinates that are within the geofence radius
        data = {
            'user_id': self.student_user.id,
            'uuid': 'test-uuid',
            'latitude': self.branch.latitude,  # Using branch coordinates
            'longitude': self.branch.longitude  # Using branch coordinates
        }
        response = self.client.post('/api/v1/attendance/attendance/check-in/', data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success')

    def test_check_out(self):
        self.client.force_authenticate(user=self.student_user)
        # First check in
        data = {
            'user_id': self.student_user.id,
            'uuid': 'test-uuid',
            'latitude': self.branch.latitude,  # Using branch coordinates
            'longitude': self.branch.longitude  # Using branch coordinates
        }
        self.client.post('/api/v1/attendance/attendance/check-in/', data)
        
        # Then check out
        response = self.client.post('/api/v1/attendance/attendance/check-out/', data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success')

    def test_get_student_attendance(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get('/api/v1/attendance/attendance/student-attendance/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.data, list))

    def test_get_supervisor_attendance(self):
        # Make sure admin user is a supervisor
        self.admin_user.is_staff = True
        self.admin_user.save()
        # Create a track with the admin user as supervisor
        track = Track.objects.create(
            name="Test Track",
            intake=1,
            supervisor=self.admin_user,
            start_date=timezone.now().date(),
            description="Test track",
            default_branch=self.branch
        )
        # Create a schedule for today
        schedule = Schedule.objects.create(
            name="Test Schedule",
            track=track,
            custom_branch=self.branch,
            created_at=timezone.now()
        )
        # Create an attendance record
        attendance = AttendanceRecord.objects.create(
            student=self.student,
            schedule=schedule
        )
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get('/api/v1/attendance/attendance/supervisor-attendance/')
        print("Response data:", response.data)  # Print response data for debugging
        self.assertEqual(response.status_code, 200)
        self.assertTrue(isinstance(response.data, list))

    def test_get_status(self):
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get('/api/v1/attendance/attendance/status/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('is_checked_in', response.data)

    def test_reset_check_ins(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(reverse('attendance-reset-check-ins'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success')

    def test_manual_attend(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            reverse('attendance-manual-attend', kwargs={'pk': self.attendance.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'success') 