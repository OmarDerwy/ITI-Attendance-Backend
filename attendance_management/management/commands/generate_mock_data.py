# your_app/management/commands/generate_mock_data.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import date, datetime, timedelta, time
import random

from attendance_management.models import (
    Schedule, Session, Student, AttendanceRecord, PermissionRequest
)
from users.models import CustomUser
from attendance_management.models import Track, Branch

class Command(BaseCommand):
    help = 'Generate mock data for testing attendance trends'

    def handle(self, *args, **kwargs):
        User = get_user_model()

        # Retrieve existing objects
        try:
            supervisor = CustomUser.objects.get(id=16)
            branch = Branch.objects.get(id=1)
            track1 = Track.objects.get(id=1)
            track2 = Track.objects.get(id=22)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))
            return

        self.stdout.write("Generating schedules...")
        schedules = []
        for i in range(14):  
            track = track1 if i % 2 == 0 else track2
            schedule = Schedule.objects.create(
            track=track,
            name=f"{track.name} Day {i + 1}",
            created_at=date(2025, 4, 1) + timedelta(days=i),
            custom_branch=branch,
            is_shared=True)

            schedules.append(schedule)

        self.stdout.write("Generating sessions for each schedule...")
        for schedule in schedules:
            Session.objects.create(
                track=schedule.track,
                schedule=schedule,
                title=f"{schedule.track.name} Session",
                instructor="Dr. Ahmed",
                start_time=timezone.make_aware(datetime.combine(schedule.created_at, time(10, 0))),
                end_time=timezone.make_aware(datetime.combine(schedule.created_at, time(14, 0))),
                session_type='offline'
            )

        self.stdout.write("Creating mock students...")
        students = []
        for i in range(10):
            email = f"student{i}@mail.com"
            if not User.objects.filter(email=email).exists():
                user = User.objects.create_user(
                    first_name= f"student{i}",
                    email=f"{email}",
                    password="test",
                    last_name="Test",
                    groups =['student']
                )
                track = track1 if i < 5 else track2
                student = Student.objects.create(
                    user=user,
                    track=track,
                    phone_uuid=None,
                    laptop_uuid=None,
                    is_checked_in=bool(i % 2)
                )
                students.append(student)
            else:
                try:
                    students.append(Student.objects.get(user__email=email))
                except Student.DoesNotExist:
                    track = track1 if i < 5 else track2
                    student = Student.objects.create(
                        user=User.objects.get(email=email),
                        track=track,
                        phone_uuid=None,
                        laptop_uuid=None,
                        is_checked_in=bool(i % 2)
                    )
                    students.append(student)


        self.stdout.write("Creating attendance records...")
        for schedule in schedules:
            for student in Student.objects.filter(track=schedule.track):
                AttendanceRecord.objects.create(
                    student=student,
                    schedule=schedule,
                    check_in_time=timezone.make_aware(datetime.combine(schedule.created_at, time(10, random.randint(0, 10)))),
                    check_out_time=timezone.make_aware(datetime.combine(schedule.created_at, time(14, random.randint(0, 10)))),
                )

        self.stdout.write("Creating permission requests...")
        for student in students:
            PermissionRequest.objects.create(
                student=student,
                request_type=random.choice(['early_leave', 'late_check_in', 'day_excuse']),
                reason="Doctor’s appointment",
                status=random.choice(['pending', 'approved', 'rejected']),
                schedule=random.choice(schedules),
                adjusted_time=timezone.now()
            )

        self.stdout.write(self.style.SUCCESS("✅ Mock data generation complete!"))
