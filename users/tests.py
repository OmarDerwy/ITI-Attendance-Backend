from rest_framework.test import APITestCase, APIClient
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status

User = get_user_model()

class test_get_students_using_supervisor(TestCase):
    """
    test what queryset would be viable for supervisor to only get their own students
    """
    # def setUp(self):
    #     self.client = APIClient()
    #     self.client.force_authenticate(user=User.objects.get(pk=16))
    #     self.url = reverse('user-list')

    user = User.objects.get(pk=16)
    track = user.tracks.first()
    
    print(track)
    

