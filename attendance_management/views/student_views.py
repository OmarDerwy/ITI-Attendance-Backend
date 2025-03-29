from rest_framework import viewsets
from ..models import Student
from ..serializers import StudentSerializer
from core.permissions import IsSupervisorUser

class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related('user', 'track').all()
    serializer_class = StudentSerializer
    permission_classes = [IsSupervisorUser] # TODO change into new permissions system
