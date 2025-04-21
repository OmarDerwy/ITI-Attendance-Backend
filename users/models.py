from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import Group
from django.utils.text import slugify
from rest_framework.exceptions import ValidationError
# Create your models here.

class CustomUserManager(BaseUserManager):
    """Custom user model manager where email is the unique identifier"""
    
    def create_user(self, email, password, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        groups = extra_fields.pop('groups', None)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        if groups:
            group_objs = Group.objects.filter(name__in=groups)
            user.groups.set(group_objs)
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

class CustomUser(AbstractUser): # FIXME order response for GET users

    username = None
    email = models.EmailField(unique=True, validators=[validate_email])
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    slug_name = models.SlugField(max_length=255, blank=True, null=True, unique=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['groups']  # Remove username from required fields

    objects = CustomUserManager()  # Use the custom manager

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['slug_name'],
                name='unique_slug_name'
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
    def delete(self, using=None, keep_parents=False):
        self.groups.clear()
        super().delete(using, keep_parents)
        
    def save(self, *args, **kwargs):
        self.first_name = self.first_name or ''
        self.last_name = self.last_name or ''
        self.slug_name = slugify(f"{self.first_name} {self.last_name}")
        # check for existing slug_name and if found then return error
        if CustomUser.objects.filter(slug_name=self.slug_name).exclude(pk=self.id).exists():
            user_name = f"{self.first_name} {self.last_name}".strip()
            raise ValidationError(f"User {self.first_name} {self.last_name} already exists.")
        super().save(*args, **kwargs)

    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)  # Save the user first
    #     if not self.groups.exists():  # If no groups are assigned
    #         student_group, created = Group.objects.get_or_create(name='student')
    #         self.groups.add(student_group)
    #     else:
    #         # Handle single string for groups and convert to list
    #         if isinstance(self.groups, str):
    #             group_names = [self.groups]
    #             group_objs = Group.objects.filter(name__in=group_names)
    #             self.groups.set(group_objs)

    #     if 'admin' in self.groups.values_list('name', flat=True):
    #         self.is_staff = True
    #         self.is_superuser = True
