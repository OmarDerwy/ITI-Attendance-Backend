from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from users.models import CustomUser
from faker import Faker

fake = Faker()

class CustomUserTests(APITestCase):
    def test_create_user(self):
        url = reverse('user-list')
        data = {
            'email': fake.email(),
            'username': fake.user_name(),
            'password': fake.password()
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(CustomUser.objects.count(), 1)
        print(data)
        print(CustomUser.objects.first().email)