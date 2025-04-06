from rest_framework import viewsets  # Importing the base class for creating viewsets
from rest_framework.decorators import action  # For defining custom actions in viewsets
from rest_framework.response import Response  # For returning HTTP responses
from django.utils.timezone import now  # Utility for working with timezones
from django.db import transaction  # For managing database transactions
from django.utils.dateparse import parse_datetime  # For parsing datetime strings
from ..models import Session, Schedule  # Importing models used in this view
from ..serializers import SessionSerializer  # Serializer for the Session model
from core import permissions  # Custom permissions module
from datetime import timedelta
class SessionViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing sessions.
    """
    queryset = Session.objects.all()  # Queryset for retrieving all session objects
    serializer_class = SessionSerializer  # Serializer class for session objects
    permission_classes = [permissions.IsStudentOrAboveUser]  # Permissions for accessing this viewset

    @action(detail=False, methods=['get'], url_path='today-by-track')
    def today_by_track(self, request):
        """
        Provide students with a quick way to view all sessions scheduled for today
        based on their assigned track.
        """
        user = request.user  # Get the logged-in user
        if not hasattr(user, 'student_profile'):  # Check if the user has a student profile
            return Response({'error': 'User is not a student'}, status=403)  # Return error if not a student

        student = user.student_profile  # Get the student's profile
        today = now().date()  # Get today's date
        # Filter sessions based on the student's track and today's date
        sessions = self.queryset.filter(
            schedule__track=student.track,
            start_time__date=today
        )

        serializer = self.get_serializer(sessions, many=True)  # Serialize the filtered sessions
        return Response(serializer.data)  # Return the serialized data as a response

    @action(detail=True, methods=['post'], url_path='request-excuse')
    def request_excuse(self, request, pk=None):
        """
        Allow students to request an excuse for a session.
        """
        attendance_record = self.get_object()  # Get the attendance record for the session
        excuse_type = request.data.get('excuse', 'none')  # Get the excuse type from the request
        # Validate the excuse type
        if excuse_type not in dict(AttendanceRecord.EXCUSE_CHOICES):
            return Response({'error': 'Invalid excuse type'}, status=400)  # Return error for invalid excuse
        attendance_record.excuse = excuse_type  # Update the excuse type
        attendance_record.save()  # Save the updated record
        return Response({'message': 'Excuse requested successfully', 'excuse': excuse_type})  # Return success message

    @action(detail=True, methods=['post'], url_path='request-early-leave')
    def request_early_leave(self, request, pk=None):
        """
        Allow students to request early leave for a session.
        """
        attendance_record = self.get_object()  # Get the attendance record for the session
        attendance_record.early_leave = 'pending'  # Set the early leave status to pending
        attendance_record.save()  # Save the updated record
        return Response({'message': 'Early leave requested successfully', 'status': 'pending'})  # Return success message

    @action(detail=False, methods=['post'], url_path='bulk-create-or-update')
    @transaction.atomic  # Ensure all operations in this method are atomic which means they will either all succeed or none will be applied
    def bulk_create_or_update(self, request):
        """
        Handle bulk creation or updating of sessions.
        """
        import logging
        logger = logging.getLogger(__name__) 

        combined_events = request.data.get('combinedEvents')  
        if not isinstance(combined_events, list):  # Validate that combinedEvents is a list
            logger.error("Invalid data format: combinedEvents is not a list.")
            return Response({'error': 'Invalid data format. Expected a list under "combinedEvents".'}, status=400)

        created_sessions = []  # List to store newly created sessions
        updated_sessions = []  # List to store updated sessions

        def get_or_create_schedule(track_id, schedule_date, custom_branch_id):
            """
            Helper function to get or create a schedule.
            """
            return Schedule.objects.get_or_create(
                track_id=track_id,
                created_at=schedule_date,
                defaults={
                    'name': f"Schedule for {schedule_date}",
                    'custom_branch_id': custom_branch_id
                }
            )

        for session_data in combined_events:  # Iterate over each session in the list
            if not isinstance(session_data, dict):  # Validate that session_data is a dictionary
                logger.error(f"Invalid session data format: {session_data}")
                return Response({'error': f'Invalid session data format: {session_data}'}, status=400)

            try:
                # Extract session data
                session_id = session_data.get('id')
                title = session_data.get('title')
                instructor = session_data.get('instructor')
                track_id = session_data.get('trackId')
                session_type = "online" if session_data.get('isOnline') else "offline"
                start_time = parse_datetime(session_data.get('start'))
                end_time = parse_datetime(session_data.get('end'))
                custom_branch_id = session_data.get('branch', {}).get('id')
                schedule_date = parse_datetime(session_data.get('schedule_date')).date() if session_data.get('schedule_date') else start_time.date()

                # Validate required fields
                if not all([title, track_id, start_time, end_time, custom_branch_id]):
                    logger.error(f"Missing required fields for session: {session_data}")
                    return Response({'error': f'Missing required fields for session: {session_data}'}, status=400)

                # Get or create the schedule
                schedule, _ = get_or_create_schedule(track_id, schedule_date, custom_branch_id)

                if session_id:  # If the session ID is provided, update the session
                    try:
                        session = Session.objects.get(id=session_id)  # Get the session by ID
                        if session.schedule.created_at != schedule_date:  # Check if the schedule date matches
                            session.delete()  # Delete the session if the dates don't match
                            session = None  # Mark session as None to create a new one
                    except Session.DoesNotExist:  # Handle case where the session does not exist
                        session = None

                    if session:  # Update the session if it exists
                        session.title = title
                        session.instructor = instructor
                        session.start_time = start_time
                        session.end_time = end_time
                        session.session_type = session_type
                        session.schedule = schedule  # Assign the correct Schedule instance
                        session.save()  # Save the updated session
                        updated_sessions.append(session)  # Add the session to the updated list
                    else:  # Create a new session
                        new_session = Session.objects.create(
                            title=title,
                            instructor=instructor,
                            track_id=track_id,
                            schedule=schedule,
                            start_time=start_time,
                            end_time=end_time,
                            session_type=session_type
                        )
                        created_sessions.append(new_session)  # Add the new session to the created list
                else:  # If no session ID is provided, create a new session
                    new_session = Session.objects.create(
                        title=title,
                        instructor=instructor,
                        track_id=track_id,
                        schedule=schedule,
                        start_time=start_time,
                        end_time=end_time,
                        session_type=session_type
                    )
                    created_sessions.append(new_session)  # Add the new session to the created list

            except Exception as e:
                logger.error(f"Error processing session data: {session_data}, Error: {str(e)}")
                return Response({'error': f"Error processing session data: {session_data}, Error: {str(e)}"}, status=400)

        # Return a response with the created and updated session IDs
        return Response({
            'message': 'Bulk operation completed successfully.',
            'created_sessions': [session.id for session in created_sessions],
            'updated_sessions': [session.id for session in updated_sessions]
        })

        
    @action(detail=False, methods=['get'], url_path='calendar-data')
    def calendar_data(self, request):
        """
        Retrieve calendar data by joining schedules with sessions.
        """
        track_id = request.query_params.get('track_id')

        # Ensure track filter is mandatory
        if not track_id:
            return Response({'error': 'Track filter is required.'}, status=400)

        sessions = self.queryset  # No period filter applied

        # Filter sessions by track
        if track_id:
            sessions = sessions.filter(schedule__track_id=track_id)

        # Ensure the query returns all matching records
        if not sessions.exists():
            return Response({'error': 'No sessions found for the given filters.'}, status=404)

        # Retrieve the required fields from sessions and their related schedules
        calendar_data = sessions.values(
            'id', 
            'title',  
            'instructor', 
            'schedule__track_id', 
            'session_type',  
            'start_time', 
            'end_time',  
            'schedule_id',  
            'schedule__custom_branch_id', 
            'schedule__custom_branch__name',
            'schedule__created_at'
        )

        # Transform the data into the desired format
        result = [
            {
                "id": session['id'],
                "title": session['title'],
                "instructor": session['instructor'],
                "track_id": session['schedule__track_id'],
                "is_online": session['session_type'] == "online",
                "start": session['start_time'],
                "end": session['end_time'],
                "branch": {
                    "id": session['schedule__custom_branch_id'],
                    "name": session['schedule__custom_branch__name']
                },
                "schedule_id": session['schedule_id'],
                "schedule_date": session['schedule__created_at']
            }
            for session in calendar_data
        ]

        return Response(result, status=200)