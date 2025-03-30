from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import Group
# Create your models here.

class CustomUserManager(BaseUserManager):
    """Custom user model manager where email is the unique identifier"""
    
    def create_user(self, email, password, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):

    username = None
    email = models.EmailField(unique=True, validators=[validate_email])
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    student_info = models.OneToOneField('attendance_management.StudentInfo', on_delete=models.CASCADE, related_name='users', null=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Remove username from required fields

    objects = CustomUserManager()  # Use the custom manager

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # Save the user first
        if not self.groups.exists():  # If no groups are assigned
            student_group, created = Group.objects.get_or_create(name='student')
            self.groups.add(student_group)
        if 'admin' in self.groups.values_list('name', flat=True):
            self.is_staff = True
            self.is_superuser = True
    #     # Auto-generate username from email if not provided
    #     if not self.username:
    #         self.username = self.email
    #     super().save(*args, **kwargs)
