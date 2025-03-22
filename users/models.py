from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
# Create your models here.

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True, validators=[validate_email])
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    phone_uuid = models.CharField(max_length=100, blank=True, null=True)
    laptop_uuid = models.CharField(max_length=100, blank=True, null=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']