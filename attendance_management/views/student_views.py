from rest_framework import viewsets
from ..models import Student
from ..serializers import StudentSerializer
from core import permissions

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if too much permissions to student
