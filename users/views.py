from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from django.core.mail import send_mail
from .models import CustomUser
# Create your views here.
from rest_framework.response import Response
@csrf_exempt
@api_view(['POST'])
def mailView(request):
    """View to handle email sending"""
    # Here you can handle the email sending logic
    send_mail(
        subject='Test Email',
        message='This is a test email sent from Django.',
        from_email='omarderwy@gmail.com',
        recipient_list=['imaginaryvenus5@gmail.com']
    )
    return Response({'message': 'Email sent successfully!'})

# @csrf_exempt
# @api_view(['POST'])
# def bulk_create_users(request):
#     """View to handle bulk user creation"""
    
#     data = request.data
#     users = data.get('users', [])
#     if not users:
#         return Response({'error': 'No user data provided'}, status=400)
#     CustomUser.objects.bulk_create([
#         CustomUser(**user) for user in users
#     ])
#     return Response({'message': 'Bulk user creation successful!'})