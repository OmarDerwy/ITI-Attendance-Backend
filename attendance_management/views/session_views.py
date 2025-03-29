from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.timezone import now
from ..models import Session
from ..serializers import SessionSerializer
from core import permissions

class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if too much permissions to student

    @action(detail=False, methods=['get'], url_path='today-by-track')
    def today_by_track(self, request):
        """
        Provide students with a quick way to view all sessions scheduled for (today)
        based on their assigned track.
        """
        user = request.user
        if not hasattr(user, 'student_profile'):
            return Response({'error': 'User is not a student'}, status=403)

        student = user.student_profile
        today = now().date()
        sessions = self.queryset.filter(
            schedule__track=student.track,
            start_time__date=today
        )

        serializer = self.get_serializer(sessions, many=True)
        return Response(serializer.data)