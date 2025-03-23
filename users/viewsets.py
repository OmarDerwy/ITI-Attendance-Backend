from . import models, serializers
from rest_framework import viewsets, permissions
from django.contrib.auth.models import Group
class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.CustomUser.objects.all().order_by('id')
    serializer_class = serializers.CustomUserSerializer

class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by('name')
    serializer_class = serializers.GroupSerializer
