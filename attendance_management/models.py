from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import CustomUser
from django.db.models import UniqueConstraint
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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

class Event(models.Model):
    description = models.TextField(blank=True, null=True)
    AUDIENCE_CHOICES = [
        ('students_only', 'Students Only'),
        ('guests_only', 'Guests Only'),
        ('both', 'Students and Guests'),
    ]
    audience_type = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='students_only')
    is_mandatory = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    target_tracks = models.ManyToManyField(
        'Track',
        related_name='events',
        blank=True,
        help_text="Specific tracks that can attend this event. Leave empty for all tracks."
    )
    registered_students = models.PositiveIntegerField(default=0)
    attended_students = models.PositiveIntegerField(default=0)
    registered_guests = models.PositiveIntegerField(default=0)
    attended_guests = models.PositiveIntegerField(default=0)


    @property
    def title(self):
        return self.schedule.name if hasattr(self, 'schedule') else None

    @property
    def branch(self):
        return self.schedule.custom_branch if hasattr(self, 'schedule') else None

class Schedule(models.Model):
    # ForeignKey from Session - related_name: sessions
    # ForeignKey from AttendanceRecord - related_name: attendance_records
    # ForeignKey from PermissionRequest - related_name: permission_requests
    track = models.ForeignKey(
        Track,  # <-- ForeignKey to Track (attendance_management.models)
        on_delete=models.CASCADE, related_name='schedules',
        null=True, blank=True
    )  # Each schedule belongs to a track
    name = models.CharField(max_length=255)
    created_at = models.DateField(db_index=True) 
    custom_branch = models.ForeignKey(
        Branch,  # <-- ForeignKey to Branch (attendance_management.models)
        on_delete=models.CASCADE, related_name='schedules'
    )  # Each schedule can have a custom_branch (Branch)
    is_shared = models.BooleanField(default=False)
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,  # Changed from SET_NULL to CASCADE
        related_name='schedule',
        null=True,
        blank=True
    )

    class Meta:
        unique_together = ('track', 'created_at')  # Define composite primary key

    def save(self, *args, **kwargs):
        if not self.custom_branch and self.track:
            self.custom_branch = self.track.default_branch
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name}"

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


class Guest(models.Model):
    user = models.OneToOneField(
        CustomUser,  # <-- OneToOne to CustomUser (users.models)
        on_delete=models.CASCADE, related_name='guest_profile'
    )  # Each guest is linked to a CustomUser
    date_of_birth = models.DateField(blank=True, null=True)
    national_id = models.CharField(max_length=20, blank=True, null=True, validators=[RegexValidator(regex=r'^\d{14}$', message="Enter a valid 14-digit national ID.")]
)
    college_name = models.CharField(max_length=255, blank=True, null=True)
    university_name = models.CharField(max_length=255, blank=True, null=True)
    gradyear = models.DateField(blank=True, null=True)
    degree_level = models.CharField(max_length=100, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - Guest"


class EventAttendanceRecord(models.Model):
    """
    Tracks attendance for event schedules, handling both students and guests.
    """
    STATUS_CHOICES = [
        ('registered', 'Registered'),
        ('attended', 'Attended'),
        ('absent', 'Absent'),
    ]

    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='event_attendance_records'
    )
    #  links to either student or guest
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='event_attendance_records',
        null=True,
        blank=True
    )
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name='event_attendance_records',
        null=True,
        blank=True
    )
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['check_in_time']),
            models.Index(fields=['check_out_time']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        constraints = [
            # Ensure either student or guest is provided, but not both
            models.CheckConstraint(
                check=(
                    models.Q(student__isnull=False, guest__isnull=True) |
                    models.Q(student__isnull=True, guest__isnull=False)
                ),
                name='event_attendance_either_student_or_guest'
            ),
            # Prevent duplicate attendance records
            models.UniqueConstraint(
                fields=['schedule', 'student'],
                name='unique_student_event_attendance',
                condition=models.Q(student__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['schedule', 'guest'],
                name='unique_guest_event_attendance',
                condition=models.Q(guest__isnull=False)
            )
        ]

    def clean(self):
        if not self.schedule.event:
            raise ValidationError("This schedule does not have an associated event.")
        
        if self.student and self.guest:
            raise ValidationError("Cannot have both student and guest for the same attendance record.")
        
        if not self.student and not self.guest:
            raise ValidationError("Must provide either student or guest.")        # Validate based on event audience type
        event_type = self.schedule.event.audience_type
        if self.student:
            if event_type == 'guests_only':
                raise ValidationError("This event is for guests only.")
            if not self.student.user.is_active:
                raise ValidationError("Student account is not active.")
            if not self.student.track.is_active:
                raise ValidationError("Student's track is not active.")
            # Check if student's track is allowed for this event
            if self.schedule.event.target_tracks.exists():
                if self.student.track not in self.schedule.event.target_tracks.all():
                    raise ValidationError("Student's track is not allowed for this event.")

        if self.guest:
            if event_type == 'students_only':
                raise ValidationError("This event is for students only.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        attendee = self.student if self.student else self.guest
        return f"Event Attendance: {attendee} - {self.schedule}"