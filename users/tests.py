from rest_framework.test import APITestCase, APIClient
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status

from attendance_management.models import Schedule, Track

User = get_user_model()

class test_get_students_using_supervisor(TestCase):
    """
    test what queryset would be viable for supervisor to only get their own students
    """
    # def setUp(self):
    #     self.client = APIClient()
    #     self.client.force_authenticate(user=User.objects.get(pk=16))
    #     self.url = reverse('user-list')

    user = User.objects.get(email='stu@stu.com')
    test = Track.objects.select_related('default_branch', 'supervisor')
    print(user)
    

