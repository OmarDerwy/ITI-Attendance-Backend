from rest_framework import viewsets
from ..models import Student
from ..serializers import StudentSerializer
from core import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

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

    # url to call this action is 
    @action(detail=False, methods=['get'], url_path='by-user-id')
    def get_student_by_user_id(self, request):
        """
        Retrieve a student with their track details by userId.
        """
        user_id = request.query_params.get('userId')
        if not user_id:
            return Response({'error': 'userId query parameter is required.'}, status=400)

        try:
            student = Student.objects.select_related('track', 'track__default_branch').get(user_id=user_id)
        except Student.DoesNotExist:
            raise NotFound({'error': 'No student found for the given userId.'})

        data = {
            'id': student.id,
            'phone_uuid': student.phone_uuid,
            'track': {
                'id': student.track.id,
                'name': student.track.name,
                'description': student.track.description,
                'program_type': student.track.program_type,
                'intake': student.track.intake,
                'start_date': student.track.start_date,
            },
            'branch': {
                'id': student.track.default_branch.id,
                'name': student.track.default_branch.name,
                'location_url': student.track.default_branch.location_url,
                'latitude': student.track.default_branch.latitude,
                'longitude': student.track.default_branch.longitude,
                'radius': student.track.default_branch.radius,
            },
        }
        return Response(data, status=200)


