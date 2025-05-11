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
        return f"{self.name} - {self.track.name}"

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
        return f"{self.user.first_name} {self.user.last_name} - {self.track.name}"
    
    def get_unexcused_absence_count(self):
        """
        Count the number of unexcused absences for this student.
        An unexcused absence is defined as an attendance record with no check-in time
        and no approved permission request.
        """
        from .models import PermissionRequest  # Import here to avoid circular import
        from django.utils import timezone
        today = timezone.now().date()
        
        # Only include records for schedules before today
        no_checkin_records = self.attendance_records.filter(
            check_in_time__isnull=True,
            schedule__created_at__lt=today
        )
        # Get all approved day excuse permission requests
        approved_excuses = PermissionRequest.objects.filter(
            student=self,
            request_type='day_excuse',
            status='approved'
        ).values_list('schedule_id', flat=True)
        
        return no_checkin_records.exclude(schedule_id__in=approved_excuses).count()
    
    def get_excused_absence_count(self):
        """
        Count the number of excused absences for this student.
        An excused absence is defined as an attendance record with no check-in time
        and an approved day_excuse permission request.
        """
        from .models import PermissionRequest  # Import here to avoid circular import
        from django.utils import timezone
        today = timezone.now().date()
        
        # Only include records for schedules before today
        no_checkin_records = self.attendance_records.filter(
            check_in_time__isnull=True,
            schedule__created_at__lt=today
        )
        approved_excuses = PermissionRequest.objects.filter(
            student=self,
            request_type='day_excuse',
            status='approved'
        ).values_list('schedule_id', flat=True)
        
        return no_checkin_records.filter(schedule_id__in=approved_excuses).count()
    
    def has_exceeded_warning_threshold(self):
        """
        Check if the student has exceeded either the excused or unexcused absence threshold.
        Returns a tuple of (has_warning, warning_type) where warning_type is either 'excused' or 'unexcused'.
        """
        program_type = self.track.program_type
        unexcused_threshold = ApplicationSetting.get_unexcused_absence_threshold(program_type)
        excused_threshold = ApplicationSetting.get_excused_absence_threshold(program_type)
        
        unexcused_count = self.get_unexcused_absence_count()
        excused_count = self.get_excused_absence_count()
        
        if unexcused_count >= unexcused_threshold:
            return True, 'unexcused'
        elif excused_count >= excused_threshold:
            return True, 'excused'
        
        return False, None

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

    def _str_(self):
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