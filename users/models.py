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
    
    def create_user(self, email, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        groups = extra_fields.pop('groups', None)
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()
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

class CustomUser(AbstractUser):
    # OneToOne from Branch - related_name: branch
    # ForeignKey from Track - related_name: tracks
    # OneToOne from Student - related_name: student_profile
    # OneToOne from Coordinator - related_name: coordinator
    # ForeignKey from Track (as supervisor) - related_name: tracks
    # ForeignKey from LostItem - related_name: lost_items
    # ForeignKey from FoundItem - related_name: found_items
    # ForeignKey from Notification - related_name: notifications
    username = None
    email = models.EmailField(unique=True, validators=[validate_email])
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    slug_name = models.SlugField(max_length=255, blank=True, null=True, unique=True)
    is_banned = models.BooleanField(default=False)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['groups']  # Remove username from required fields
    #add a photo_url field:
    photo_url = models.URLField(blank=True, null=True)

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
        
        # Check for existing slug_name but exclude the current instance
        if self.pk:  # If this is an existing user (has a primary key)
            duplicate_users = CustomUser.objects.filter(slug_name=self.slug_name).exclude(pk=self.pk)
        else:  # If this is a new user (no primary key yet)
            duplicate_users = CustomUser.objects.filter(slug_name=self.slug_name)
            
        if duplicate_users.exists():#.exists? 
            user_name = f"{self.first_name} {self.last_name}".strip()
            raise ValidationError(f"User {self.first_name} {self.last_name} already exists.")
            
        super().save(*args, **kwargs)
