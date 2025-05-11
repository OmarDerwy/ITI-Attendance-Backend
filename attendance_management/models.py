from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import CustomUser
from django.db.models import UniqueConstraint
from django.core.exceptions import ValidationError
from django.conf import settings
from .settings_models import ApplicationSetting

class Branch(models.Model):
    # ForeignKey from Track - related_name: tracks
    # ForeignKey from Schedule - related_name: schedules
    # ForeignKey from CoordinatorAssignment - related_name: coordinator
    name = models.CharField(max_length=255, unique=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_url = models.URLField(blank=True, null=True)
    radius = models.FloatField(validators=[MinValueValidator(0)])
    branch_manager = models.OneToOneField(
        CustomUser,  # <-- ForeignKey to CustomUser (users.models)
        on_delete=models.CASCADE, related_name='branch', null=True, blank=True
    )  # Each branch has a branch_manager (CustomUser)

    def __str__(self):
        return self.name

class Coordinator(models.Model):
    # OneToOne to CustomUser (each coordinator is assigned to only one branch)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='coordinator'
    )
    # ForeignKey to Branch (each branch can have multiple coordinators)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='coordinators'
    )

    def __str__(self):
        return f"Coordinator: {self.user} -> Branch: {self.branch}"

class Track(models.Model):
    # ForeignKey from Session - related_name: sessions
    # ForeignKey from Student - related_name: students
    # ForeignKey from Schedule - related_name: schedules
    name = models.CharField(max_length=255)
    supervisor = models.ForeignKey(
        CustomUser,  # <-- ForeignKey to CustomUser (users.models)
        on_delete=models.CASCADE, related_name='tracks'
    )  # Each track has a supervisor (CustomUser)
    intake = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(254)])
    start_date = models.DateField()
    is_active = models.BooleanField(default=True)
    description = models.TextField()
    default_branch = models.ForeignKey(
        Branch,  # <-- ForeignKey to Branch (attendance_management.models)
        on_delete=models.CASCADE, related_name='tracks'
    )  # Each track has a default_branch (Branch)
    PROGRAM_CHOICES = [
        ('intensive', 'Intensive Program'),
        ('nine_months', '9 months'),
    ]
    program_type = models.CharField(max_length=20, choices=PROGRAM_CHOICES, default='nine_months')

    def __str__(self):
        return self.name

class Schedule(models.Model):
    # ForeignKey from Session - related_name: sessions
    # ForeignKey from AttendanceRecord - related_name: attendance_records
    # ForeignKey from PermissionRequest - related_name: permission_requests
    track = models.ForeignKey(
        Track,  # <-- ForeignKey to Track (attendance_management.models)
        on_delete=models.CASCADE, related_name='schedules'
    )  # Each schedule belongs to a track
    name = models.CharField(max_length=255)
    created_at = models.DateField(db_index=True) 
    custom_branch = models.ForeignKey(
        Branch,  # <-- ForeignKey to Branch (attendance_management.models)
        on_delete=models.CASCADE, related_name='schedules'
    )  # Each schedule can have a custom_branch (Branch)
    is_shared = models.BooleanField(default=False)

    class Meta:
        unique_together = ('track', 'created_at')  # Define composite primary key

    def save(self, *args, **kwargs):
        if not self.custom_branch and self.track:
            self.custom_branch = self.track.default_branch
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}"

    @property
    def start_time(self):
        """
        Get the start time from the first session of the day using prefetched data if available.
        """
        sessions = getattr(self, 'prefetched_sessions', None)
        if sessions is None:
            sessions = self.sessions.all()
        first_session = min(sessions, key=lambda s: s.start_time, default=None)
        return first_session.start_time if first_session else None

    @property
    def end_time(self):
        """
        Get the end time from the last session of the day using prefetched data if available.
        """
        sessions = getattr(self, 'prefetched_sessions', None)
        if sessions is None:
            sessions = self.sessions.all()
        last_session = max(sessions, key=lambda s: s.end_time, default=None)
        return last_session.end_time if last_session else None

    @property
    def attended_out_of_total(self):
        """
        Calculate the number of students attended the schedule out of total students in the track using the available attendance records.
        Uses prefetched attendance_records if available.
        """
        attendance_records = getattr(self, 'prefetched_attendance_records', None)
        if attendance_records is None:
            attendance_records = self.attendance_records.all()
        total_students = len(attendance_records)
        attended_students = len({ar.student_id for ar in attendance_records if ar.check_in_time is not None})
        return {
            "attended": attended_students,
            "total": total_students
        }

class Session(models.Model):
    # ForeignKey from nothing (leaf model)
    COURSE_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
    ]
    schedule = models.ForeignKey(
        Schedule,  # <-- ForeignKey to Schedule (attendance_management.models)
        on_delete=models.CASCADE, related_name='sessions'
    )  # Each session belongs to a schedule
    title = models.CharField(max_length=255)
    instructor = models.CharField(max_length=255, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    session_type = models.CharField(max_length=10, choices=COURSE_CHOICES, default='offline')
    room = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.title}"

class Student(models.Model):  # Renamed from StudentInfo
    # ForeignKey from AttendanceRecord - related_name: attendance_records
    # ForeignKey from PermissionRequest - related_name: permission_requests
    user = models.OneToOneField(
        CustomUser,  # <-- OneToOne to CustomUser (users.models)
        on_delete=models.CASCADE, related_name='student_profile'
    )  # Each student is linked to a CustomUser
    track = models.ForeignKey(
        Track,  # <-- ForeignKey to Track (attendance_management.models)
        on_delete=models.CASCADE, related_name='students'
    )  # Each student belongs to a track
    phone_uuid = models.CharField(max_length=100, blank=True, null=True)
    laptop_uuid = models.CharField(max_length=100, blank=True, null=True)
    is_checked_in = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user}"
    
    @property
    def unexcused_absences(self):
        """
        Count the number of unexcused absences for this student.
        An unexcused absence is defined as an attendance record with no check-in time
        and no approved permission request.
        """
        attendance_records = self._get_attendance_records_cache()
        permission_requests = self._get_permission_requests_cache()
        if attendance_records is None:
            attendance_records = getattr(self, 'prefetched_attendance_records', None)
            if attendance_records is None:
                no_checkin_records = self.attendance_records.select_related('schedule').filter(check_in_time__isnull=True)
            else:
                no_checkin_records = [ar for ar in attendance_records if ar.check_in_time is None]
        else:
            no_checkin_records = [ar for ar in attendance_records if ar.check_in_time is None and ar.student_id == self.id]
        # Use cached permission requests
        if permission_requests is not None:
            approved_excuses = {pr.schedule_id for pr in permission_requests if pr.student_id == self.id and pr.request_type == 'day_excuse' and pr.status == 'approved'}
        else:
            from .models import PermissionRequest
            approved_excuses = set(PermissionRequest.objects.filter(
                student=self,
                request_type='day_excuse',
                status='approved'
            ).values_list('schedule_id', flat=True))
        if hasattr(no_checkin_records, 'exclude'):
            return no_checkin_records.exclude(schedule_id__in=approved_excuses).count()
        else:
            return len([ar for ar in no_checkin_records if ar.schedule_id not in approved_excuses])

    @property
    def excused_absences(self):
        """
        Count the number of excused absences for this student.
        An excused absence is defined as an attendance record with no check-in time
        and an approved day_excuse permission request.
        """
        attendance_records = self._get_attendance_records_cache()
        permission_requests = self._get_permission_requests_cache()
        if attendance_records is None:
            attendance_records = getattr(self, 'prefetched_attendance_records', None)
            if attendance_records is None:
                no_checkin_records = self.attendance_records.select_related('schedule').filter(check_in_time__isnull=True)
            else:
                no_checkin_records = [ar for ar in attendance_records if ar.check_in_time is None]
        else:
            no_checkin_records = [ar for ar in attendance_records if ar.check_in_time is None and ar.student_id == self.id]
        # Use cached permission requests
        if permission_requests is not None:
            approved_excuses = {pr.schedule_id for pr in permission_requests if pr.student_id == self.id and pr.request_type == 'day_excuse' and pr.status == 'approved'}
        else:
            from .models import PermissionRequest
            approved_excuses = set(PermissionRequest.objects.filter(
                student=self,
                request_type='day_excuse',
                status='approved'
            ).values_list('schedule_id', flat=True))
        if hasattr(no_checkin_records, 'filter'):
            return no_checkin_records.filter(schedule_id__in=approved_excuses).count()
        else:
            return len([ar for ar in no_checkin_records if ar.schedule_id in approved_excuses])

    @property
    def warning_status(self):
        """
        Check if the student has exceeded either the excused or unexcused absence threshold.
        Returns warning_type: either 'excused', 'unexcused', or None.
        """
        program_type = self.track.program_type

        # Use static/process-level cache for ApplicationSetting
        cache = self._get_settings_cache()
        excused_key = f'excused_absence_threshold_{program_type}'
        unexcused_key = f'unexcused_absence_threshold_{program_type}'

        if excused_key not in cache or unexcused_key not in cache:
            from .settings_models import ApplicationSetting
            settings = ApplicationSetting.objects.filter(
                key__in=[excused_key, unexcused_key]
            )
            for s in settings:
                cache[s.key] = int(s.value)
            cache.setdefault(excused_key, 3)
            cache.setdefault(unexcused_key, 3)

        excused_threshold = cache[excused_key]
        unexcused_threshold = cache[unexcused_key]

        if self.unexcused_absences >= unexcused_threshold:
            return 'unexcused'
        elif self.excused_absences >= excused_threshold:
            return 'excused'
        return None

    @staticmethod
    def _get_settings_cache():
        # Static cache for ApplicationSetting
        if not hasattr(Student, '_settings_cache'):
            Student._settings_cache = {}
        return Student._settings_cache

    @staticmethod
    def _get_attendance_records_cache():
        """
        Static/process-level cache for all attendance records.
        Returns a list of AttendanceRecord objects for all students, or None if not yet cached.
        """
        if not hasattr(Student, '_attendance_records_cache'):
            try:
                from .models import AttendanceRecord
                Student._attendance_records_cache = list(AttendanceRecord.objects.all())
            except Exception:
                Student._attendance_records_cache = None
        return Student._attendance_records_cache

    @staticmethod
    def _get_permission_requests_cache():
        """
        Static/process-level cache for all permission requests.
        Returns a list of PermissionRequest objects for all students, or None if not yet cached.
        """
        if not hasattr(Student, '_permission_requests_cache'):
            try:
                from .models import PermissionRequest
                Student._permission_requests_cache = list(PermissionRequest.objects.all())
            except Exception:
                Student._permission_requests_cache = None
        return Student._permission_requests_cache

class AttendanceRecord(models.Model):
    # ForeignKey from nothing (leaf model)
    STATUS_CHOICES = [
        ('attended', 'Attended'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
        ('excused_late', 'Excused Late'),
        ('no-check-out', 'No Check-out'),
        ('late-check-in_no-check-out', 'Late Check-in & No Check-out'),
        ('pending', 'Pending'),
    ]
    PERMISSION_CHOICES = [
        ('none', 'None'),
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
    ]
    student = models.ForeignKey(
        'Student',  # <-- ForeignKey to Student (attendance_management.models)
        on_delete=models.CASCADE, related_name='attendance_records'
    )  # Each attendance record is for a student
    schedule = models.ForeignKey(
        'Schedule',  # <-- ForeignKey to Schedule (attendance_management.models)
        on_delete=models.CASCADE, related_name='attendance_records'
    )  # Each attendance record is for a schedule
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='absent')
    
    class Meta:
        indexes = [
            models.Index(fields=['check_in_time']),
            models.Index(fields=['check_out_time']),
            models.Index(fields=['student']),
            models.Index(fields=['schedule']),
            models.Index(fields=['status']),  # Add index for the new status field
        ]

    def __str__(self):
        return f"AttendanceRecord(Student: {self.student}, Schedule: {self.schedule})"

class PermissionRequest(models.Model):
    # ForeignKey from nothing (leaf model)
    REQUEST_TYPES = [
        ('early_leave', 'Early Leave'),
        ('late_check_in', 'Late Check-In'),
        ('day_excuse', 'Day Excuse'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    student = models.ForeignKey(
        'Student',  # <-- ForeignKey to Student (attendance_management.models)
        on_delete=models.CASCADE, related_name='permission_requests'
    )  # Each permission request is for a student
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    schedule = models.ForeignKey(
        'Schedule',  # <-- ForeignKey to Schedule (attendance_management.models)
        on_delete=models.CASCADE, related_name='permission_requests', null=True, blank=True
    )  # Each permission request can be for a schedule
    adjusted_time = models.DateTimeField(blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.request_type} ({self.status})"
