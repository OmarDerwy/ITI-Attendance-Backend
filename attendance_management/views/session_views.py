from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.utils.timezone import now
from ..models import Session, Schedule, Track
from ..serializers import SessionSerializer
from core import permissions

class SessionViewSet(viewsets.ModelViewSet):
    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = [permissions.IsStudentOrAboveUser] # CHECK if too much permissions to student

    
    def perform_create(self, serializer):
        """
        Override create to:
        1. Use trackId to select which track to assign the schedule to
        2. Create a new schedule if one doesn't exist
        3. Check for existing sessions on the same day
        4. Update schedule name for first sessions
        """
        validated_data = serializer.validated_data
        start_time = validated_data.get('start_time')
        session_date = start_time.date()
        
        # Get track_id from request data
        track_id = self.request.data.get('trackId')
        if not track_id:
            raise ValidationError({'error': 'trackId is required'})
            
        try:
            track = Track.objects.get(id=track_id)
        except Track.DoesNotExist:
            raise ValidationError({'error': 'Track not found'})
            
        # Check if schedule exists or create new one
        schedule = validated_data.get('schedule')
        if not schedule:
            # Create a new schedule
            session_name = validated_data.get('name', f"Session on {session_date}")
            schedule = Schedule.objects.create(
                track=track,
                name=session_name,
                created_at=start_time,
                custom_branch=''
            )
            validated_data['schedule'] = schedule
        
        # Check if a session already exists for the same day
        existing_session = Session.objects.filter(
            schedule=schedule, 
            start_time__date=session_date
        ).exists()
        
        if existing_session:
            raise ValidationError({'error': 'A session already exists for this schedule on the same day'})
        
        # Save the new session
        session = serializer.save(schedule=schedule)
        
        # Update schedule name if this is the first session
        if Session.objects.filter(schedule=schedule).count() == 1:
            schedule.name = getattr(session, 'name', f"Session on {session_date}")
            schedule.save()

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        
        # Check if the user is a supervisor
        if user.groups.filter(name="supervisor").exists():
            # Get tracks supervised by this user
            supervised_tracks = user.tracks.all()
            if supervised_tracks:
                # Get courses for these tracks
                allRelatedSchedules = Schedule.objects.filter(track__in=supervised_tracks)
                relatedSessions = Session.objects.filter(schedule__in=allRelatedSchedules).distinct()
                # Filter sessions by these courses
                queryset = relatedSessions
        
        return queryset

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

    @action(detail=True, methods=['post'], url_path='request-excuse')
    def request_excuse(self, request, pk=None):
        """
        Allow students to request an excuse for a session.
        """
        attendance_record = self.get_object()
        excuse_type = request.data.get('excuse', 'none')
        if excuse_type not in dict(AttendanceRecord.EXCUSE_CHOICES):
            return Response({'error': 'Invalid excuse type'}, status=400)
        attendance_record.excuse = excuse_type
        attendance_record.save()
        return Response({'message': 'Excuse requested successfully', 'excuse': excuse_type})

    @action(detail=True, methods=['post'], url_path='request-early-leave')
    def request_early_leave(self, request, pk=None):
        """
        Allow students to request early leave for a session.
        """
        attendance_record = self.get_object()
        attendance_record.early_leave = 'pending'
        attendance_record.save()
        return Response({'message': 'Early leave requested successfully', 'status': 'pending'})