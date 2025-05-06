from django.db.models.signals import post_migrate
from django.contrib.auth.models import Group
from django.dispatch import receiver

@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    # Define the required groups
    required_groups = ['admin', 'supervisor', 'instructor', 'student', 'coordinator', 'branch-manager', 'guest']
    
    for group_name in required_groups:
        Group.objects.get_or_create(name=group_name)