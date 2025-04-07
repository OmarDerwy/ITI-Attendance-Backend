from rest_framework import viewsets
from ..models import Student
from ..serializers import StudentSerializer
from core import permissions

# class CustomPagination(PageNumberPagination):
#     page_size = 10  # 10 students per page
class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()  # Updated to use Student
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]  # CHECK if too much permissions to student

