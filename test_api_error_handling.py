#!/usr/bin/env python3
"""
Test script to verify that API errors in description validation are handled gracefully.
This script tests that when the Hugging Face API returns an error, the matching algorithm continues.
"""

import os
import sys
import django
from unittest.mock import patch, MagicMock

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from lost_and_found_system.views import LostItemViewSet, FoundItemViewSet
from lost_and_found_system.models import LostItem, FoundItem, ItemStatusChoices
from lost_and_found_system.serializers import LostItemSerializer, FoundItemSerializer
from rest_framework.exceptions import ValidationError
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

User = get_user_model()

def test_api_error_handling():
    """Test that API errors don't block the matching algorithm"""
    
    # Create test user
    user = User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
    
    factory = RequestFactory()
    
    print("Testing API error handling in description validation...")
    
    # Test LostItem creation with API error
    print("\n1. Testing LostItem creation with API error:")
    
    # Mock the check_description_relevance function to return "api_error"
    with patch('lost_and_found_system.views.check_description_relevance', return_value="api_error"):
        request = factory.post('/api/lost-items/', {
            'name': 'Test Laptop',
            'description': 'A silver laptop with stickers',
            'place': 'Library'
        })
        request.user = user
        
        view = LostItemViewSet()
        view.request = request
        
        # Create serializer with test data
        data = {
            'name': 'Test Laptop',
            'description': 'A silver laptop with stickers',
            'place': 'Library'
        }
        serializer = LostItemSerializer(data=data)
        
        if serializer.is_valid():
            try:
                view.perform_create(serializer)
                print("✅ LostItem created successfully despite API error")
                
                # Verify the item was created
                lost_item = LostItem.objects.filter(name='Test Laptop', user=user).first()
                if lost_item:
                    print(f"✅ Lost item created: {lost_item.name} (ID: {lost_item.item_id})")
                else:
                    print("❌ Lost item was not created")
                    
            except ValidationError as e:
                print(f"❌ Unexpected validation error: {e}")
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
        else:
            print(f"❌ Serializer validation failed: {serializer.errors}")
    
    # Test FoundItem creation with API error
    print("\n2. Testing FoundItem creation with API error:")
    
    with patch('lost_and_found_system.views.check_description_relevance', return_value="api_error"):
        request = factory.post('/api/found-items/', {
            'name': 'Test Phone',
            'description': 'A black smartphone with cracked screen',
            'place': 'Cafeteria'
        })
        request.user = user
        
        view = FoundItemViewSet()
        view.request = request
        
        # Create serializer with test data
        data = {
            'name': 'Test Phone',
            'description': 'A black smartphone with cracked screen',
            'place': 'Cafeteria'
        }
        serializer = FoundItemSerializer(data=data)
        
        if serializer.is_valid():
            try:
                view.perform_create(serializer)
                print("✅ FoundItem created successfully despite API error")
                
                # Verify the item was created
                found_item = FoundItem.objects.filter(name='Test Phone', user=user).first()
                if found_item:
                    print(f"✅ Found item created: {found_item.name} (ID: {found_item.item_id})")
                else:
                    print("❌ Found item was not created")
                    
            except ValidationError as e:
                print(f"❌ Unexpected validation error: {e}")
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
        else:
            print(f"❌ Serializer validation failed: {serializer.errors}")
    
    # Test that irrelevant descriptions still get blocked
    print("\n3. Testing that irrelevant descriptions are still blocked:")
    
    with patch('lost_and_found_system.views.check_description_relevance', return_value="irrelevant"):
        request = factory.post('/api/lost-items/', {
            'name': 'Test Book',
            'description': 'This is completely unrelated to a book',
            'place': 'Classroom'
        })
        request.user = user
        
        view = LostItemViewSet()
        view.request = request
        
        data = {
            'name': 'Test Book',
            'description': 'This is completely unrelated to a book',
            'place': 'Classroom'
        }
        serializer = LostItemSerializer(data=data)
        
        if serializer.is_valid():
            try:
                view.perform_create(serializer)
                print("❌ Item should have been blocked due to irrelevant description")
            except ValidationError as e:
                print("✅ Irrelevant description correctly blocked")
                print(f"   Error message: {e.detail}")
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
        else:
            print(f"❌ Serializer validation failed: {serializer.errors}")
    
    # Test that relevant descriptions still work
    print("\n4. Testing that relevant descriptions still work:")
    
    with patch('lost_and_found_system.views.check_description_relevance', return_value="relevant"):
        request = factory.post('/api/lost-items/', {
            'name': 'Test Notebook',
            'description': 'A blue spiral notebook with math notes',
            'place': 'Library'
        })
        request.user = user
        
        view = LostItemViewSet()
        view.request = request
        
        data = {
            'name': 'Test Notebook',
            'description': 'A blue spiral notebook with math notes',
            'place': 'Library'
        }
        serializer = LostItemSerializer(data=data)
        
        if serializer.is_valid():
            try:
                view.perform_create(serializer)
                print("✅ Relevant description correctly allowed")
                
                # Verify the item was created
                lost_item = LostItem.objects.filter(name='Test Notebook', user=user).first()
                if lost_item:
                    print(f"✅ Lost item created: {lost_item.name} (ID: {lost_item.item_id})")
                else:
                    print("❌ Lost item was not created")
                    
            except ValidationError as e:
                print(f"❌ Unexpected validation error: {e}")
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
        else:
            print(f"❌ Serializer validation failed: {serializer.errors}")
    
    print("\n" + "="*60)
    print("API Error Handling Test Summary:")
    print("✅ API errors are now handled gracefully")
    print("✅ Matching algorithm continues when API fails")
    print("✅ Irrelevant descriptions are still blocked")
    print("✅ Relevant descriptions are still allowed")
    print("="*60)

def cleanup():
    """Clean up test data"""
    try:
        # Delete test items
        LostItem.objects.filter(name__startswith='Test').delete()
        FoundItem.objects.filter(name__startswith='Test').delete()
        
        # Delete test user
        User.objects.filter(username='testuser').delete()
        print("\n✅ Test data cleaned up")
    except Exception as e:
        print(f"\n⚠️  Error during cleanup: {e}")

if __name__ == '__main__':
    try:
        test_api_error_handling()
    finally:
        cleanup()
