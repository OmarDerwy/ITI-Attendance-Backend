from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import CustomUser
from django.db.models import UniqueConstraint

class Branch(models.Model):
    name = models.CharField(max_length=255)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_url = models.URLField(blank=True, null=True)
    radius = models.FloatField(validators=[MinValueValidator(0)])

    def __str__(self):
        return self.name
    
class Track(models.Model):
    name = models.CharField(max_length=255)
    supervisor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='tracks')
    intake = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(254)])
    start_date = models.DateField()
    description = models.TextField()
    default_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='tracks')
    PROGRAM_CHOICES = [
        ('intensive', 'Intensive Program'),
        ('nine_months', '9 months'),
    ]
    program_type = models.CharField(max_length=20, choices=PROGRAM_CHOICES, default='nine_months')

    def __str__(self):
        return self.name

class Schedule(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='Schedules')
    name = models.CharField(max_length=255)
    created_at = models.DateField(auto_now_add=True)  # Changed to DateField
    custom_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='Schedules')
    is_shared = models.BooleanField(default=False)

    class Meta:
        unique_together = ('track', 'created_at')  # Define composite primary key

    def save(self, *args, **kwargs):
        if not self.custom_branch and self.track:
            self.custom_branch = self.track.default_branch
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Session(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='schedules')
    COURSE_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
    ]
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=255)
    instructor = models.CharField(max_length=255, null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    session_type = models.CharField(max_length=10, choices=COURSE_CHOICES, default='offline')

    def __str__(self):
        return f"{self.title}"

class Student(models.Model):  # Renamed from StudentInfo
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='students')
    phone_uuid = models.CharField(max_length=100, blank=True, null=True)
    laptop_uuid = models.CharField(max_length=100, blank=True, null=True)
    is_checked_in = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.track.name}"

class AttendanceRecord(models.Model):
    PERMISSION_CHOICES = [
        ('none', 'None'),
        ('approved', 'Approved'),
        ('pending', 'Pending'),
        ('rejected', 'Rejected'),
    ]
    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='attendance_records')
    schedule = models.ForeignKey('Schedule', on_delete=models.CASCADE, related_name='attendance_records')
    check_in_time = models.DateTimeField(blank=True, null=True)
    check_out_time = models.DateTimeField(blank=True, null=True)
    excuse = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default='none')
    early_leave = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default='none')
    late_check_in = models.CharField(max_length=255, choices=PERMISSION_CHOICES, blank=True, null=True)

    def __str__(self):
        return f"AttendanceRecord(Student: {self.student}, Schedule: {self.schedule})"


class PermissionRequest(models.Model):
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

    student = models.ForeignKey('Student', on_delete=models.CASCADE, related_name='permission_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPES)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    schedule = models.ForeignKey('Schedule', on_delete=models.CASCADE, related_name='permission_requests', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student} - {self.request_type} ({self.status})"


