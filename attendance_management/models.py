from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import CustomUser

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
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='tracks')  # Updated field

    def __str__(self):
        return self.name

class Schedule(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='schedules')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Session(models.Model):
    COURSE_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
    ]

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='sessions')
    title = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    session_type = models.CharField(max_length=10, choices=COURSE_CHOICES, default='offline')

    def __str__(self):
        return f"{self.title} ({self.start_time} - {self.end_time})"

class StudentInfo(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name='students')
    phone_uuid = models.CharField(max_length=100, blank=True, null=True)
    laptop_uuid = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.track.name}"
