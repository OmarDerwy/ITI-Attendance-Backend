from rest_framework import viewsets
from ..models import Student
from ..serializers import StudentSerializer
from core import permissions
from rest_framework.pagination import PageNumberPagination

class CustomPagination(PageNumberPagination):
    page_size = 10  # 10 students per page
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        for key in ['next', 'previous']:
            link = response.data.get(key)
            if link:
                response.data[key] = link.replace("http://localhost:8000/api/v1/", "") # TODO change this as soon as possible
        return response
class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()  # Updated to use Student
    serializer_class = StudentSerializer
    permission_classes = [permissions.IsStudentOrAboveUser]  # CHECK if too much permissions to student
    pagination_class = CustomPagination  # added custom pagination

