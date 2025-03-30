from rest_framework import viewsets
from ..models import StudentInfo
from ..serializers import StudentSerializer
from core import permissions

class StudentViewSet(viewsets.ModelViewSet):
    queryset = StudentInfo.objects.select_related('user', 'track').all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if too much permissions to student
