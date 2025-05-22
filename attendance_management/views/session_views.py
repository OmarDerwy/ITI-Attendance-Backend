from rest_framework import viewsets  # Importing the base class for creating viewsets
from rest_framework.decorators import action  # For defining custom actions in viewsets
from rest_framework.response import Response  # For returning HTTP responses
from django.utils.timezone import now  # Utility for working with timezones
from django.db import transaction  # For managing database transactions
from django.utils.dateparse import parse_datetime  # For parsing datetime strings
from ..models import Session, Schedule , Student , AttendanceRecord , Branch 
from ..serializers import SessionSerializer  # Serializer for the Session model
from core import permissions  # Custom permissions module
from datetime import timedelta
from django.db.models import Count  # Import Count for aggregation

# Calender views
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

    @action(detail=False, methods=['post'], url_path='bulk-create-or-update')
    @transaction.atomic  # Ensure all operations in this method are atomic which means they will either all succeed or none will be applied
    def bulk_create_or_update(self, request):
        """
        Handle bulk creation, updating, or deletion of sessions.
        """
        import logging
        logger = logging.getLogger(__name__) 

        combined_events = request.data.get('combinedEvents', [])  
        deleted_events = request.data.get('deletedEvents', [])
        
        if not isinstance(combined_events, list):  # Validate that combinedEvents is a list
            logger.error("Invalid data format: combinedEvents is not a list.")
            return Response({'error': 'Invalid data format. Expected a list under "combinedEvents".'}, status=400)
            
        if not isinstance(deleted_events, list):  # Validate that deletedEvents is a list
            logger.error("Invalid data format: deletedEvents is not a list.")
            return Response({'error': 'Invalid data format. Expected a list under "deletedEvents".'}, status=400)

        created_sessions = []  # List to store newly created sessions
        updated_sessions = []  # List to store updated sessions
        deleted_sessions = []  # List to store deleted sessions
        deleted_schedules = []  # List to store deleted schedules

        def get_or_create_schedule(track_id, schedule_date, custom_branch_id):
            """
            Helper function to get or create a schedule.
            Find a schedule for the given track and date, or create one if it doesn't exist.
            If a schedule is created, add attendance records for all students in the track.
            """
            try:
                # Try to find a schedule for this track and date
                schedule = Schedule.objects.filter(
                    track_id=track_id,
                    created_at=schedule_date
                ).first()
                
                if schedule:
                    # If found, return the existing schedule
                    return schedule, False
                else:
                    # If not found, create a new schedule
                    branch = Branch.objects.get(id=custom_branch_id)  # Fetch the Branch object
                    schedule = Schedule.objects.create(
                        track_id=track_id,
                        created_at=schedule_date,
                        name=f"Schedule for {schedule_date}",
                        custom_branch=branch
                    )

                    # Add attendance records for all students in the track
                    students = Student.objects.filter(
                        track_id=track_id,
                        user__is_active=True  # Ensure the student is active
                        )
                    attendance_records = [
                        AttendanceRecord(
                            student=student,
                            schedule=schedule,
                            check_in_time=None,
                            check_out_time=None
                        )
                        for student in students
                    ]
                    AttendanceRecord.objects.bulk_create(attendance_records)

                    return schedule, True
            except Exception as e:  # Fixed syntax error in exception handling
                logger.error(f"Error getting or creating schedule: {str(e)}")  # Fixed logging statement
                raise e

        # Process deletions first
        for session_id in deleted_events:
            try:
                session = Session.objects.get(id=session_id)
                schedule = session.schedule
                
                # Delete the session
                session.delete()
                deleted_sessions.append(session_id)
                
                # Check if the schedule is now empty (no more sessions)
                if not schedule.sessions.exists():
                    # Delete attendance records associated with the schedule
                    # (will be deleted automatically due to CASCADE)
                    schedule_id = schedule.id
                    schedule.delete()
                    deleted_schedules.append(schedule_id)
                    
            except Session.DoesNotExist:
                logger.warning(f"Attempted to delete non-existent session with ID: {session_id}")
            except Exception as e:
                logger.error(f"Error deleting session with ID {session_id}: {str(e)}")
                return Response({'error': f"Error deleting session with ID {session_id}: {str(e)}"}, status=400)

        # Process creation and updates
        for session_data in combined_events:  
            if not isinstance(session_data, dict):  # Validate that session_data is a dictionary
                logger.error(f"Invalid session data format: {session_data}")  # Fixed logging statement
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
                room = session_data.get('room')
                custom_branch_id = session_data.get('branch', {}).get('id')
                schedule_date = parse_datetime(session_data.get('schedule_date')).date() if session_data.get('schedule_date') else start_time.date()

                # Get or create the schedule
                schedule, _ = get_or_create_schedule(track_id, start_time.date(), custom_branch_id)

                if session_id:  # If the session ID is provided, update the session
                    try:
                        session = Session.objects.get(id=session_id)  # Get the session by ID
                        # Instead of deleting the session when schedule date changes, 
                        # just update the session with the new schedule
                    except Session.DoesNotExist:  # Handle case where the session does not exist
                        session = None

                    if session:  # Update the session if it exists
                        if custom_branch_id and schedule.custom_branch_id != custom_branch_id:
                            try:
                                new_branch = Branch.objects.get(id=custom_branch_id)
                                schedule.custom_branch = new_branch
                                schedule.save(update_fields=['custom_branch'])
                                logger.info(f"Updated schedule {schedule.id} with new branch {custom_branch_id}")
                            except Branch.DoesNotExist:
                                logger.error(f"Branch with id {custom_branch_id} not found")
                                return Response({'error': f'Branch with id {custom_branch_id} not found'}, status=400)

                        session.title = title
                        session.instructor = instructor
                        session.start_time = start_time
                        session.end_time = end_time
                        session.room = room
                        session.session_type = session_type
                        # Always assign the proper schedule based on the new date
                        # This handles moving sessions between days
                        session.schedule = schedule 
                        session.save()  # Save the updated session
                        updated_sessions.append(session)  # Add the session to the updated list
                    else:  # Create a new session
                        new_session = Session.objects.create(
                            title=title,
                            instructor=instructor,
                            # track_id=track_id,
                            schedule=schedule,
                            start_time=start_time,
                            end_time=end_time,
                            room=room,
                            session_type=session_type
                        )
                        created_sessions.append(new_session)  # Add the new session to the created list
                else:  # If no session ID is provided, create a new session
                    new_session = Session.objects.create(
                        title=title,
                        instructor=instructor,
                        # track_id=track_id,
                        schedule=schedule,
                        start_time=start_time,
                        end_time=end_time,
                        room=room,
                        session_type=session_type
                    )
                    created_sessions.append(new_session)  # Add the new session to the created list

            except Exception as e:
                logger.error(f"Error processing session data: {session_data}, Error: {str(e)}")
                return Response({'error': f"Error processing session data: {session_data}, Error: {str(e)}"}, status=400)
        # Cleanup: Delete attendance records for schedules with no associated sessions
        empty_schedules = Schedule.objects.filter(
            sessions__isnull=True
        )
        empty_schedules_count = empty_schedules.count()

        # Attendance records will now be deleted automatically due to cascading
        empty_schedules.delete()
        # Return a response with the created and updated session IDs
        return Response(status=200, data={
            'message': 'Bulk operation completed successfully.',
            'created_sessions': [session.id for session in created_sessions],
            'updated_sessions': [session.id for session in updated_sessions],
            'deleted_sessions': deleted_sessions,
            'deleted_schedules': deleted_schedules,
            'deleted_empty_schedules_count': empty_schedules_count
        })

        
    @action(detail=False, methods=['get'], url_path='calendar-data')
    def calendar_data(self, request):
        """
        Retrieve calendar data by joining schedules with sessions.
        """
        request_user = self.request.user
        if not hasattr(request_user, 'student_profile'):
            track_id = request.query_params.get('track_id')
        else:
            student = request_user.student_profile
            track_id = student.track.id

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
            'room',
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
                "room": session['room'],
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

    # def destroy(self, request, *args, **kwargs):
    #     """
    #     Override destroy to ensure the session is deleted, and if the schedule becomes empty,
    #     delete the schedule and its associated attendance records.
    #     """
    #     instance = self.get_object()
    #     schedule = instance.schedule

    #     # Delete the session
    #     instance.delete()

    #     # Check if the schedule is now empty
    #     if not schedule.sessions.exists():
    #         # Delete attendance records associated with the schedule
    #         schedule.attendance_records.all().delete()

    #         # Delete the schedule itself
    #         schedule.delete()

    #     return Response({'message': 'Session deleted successfully. Schedule and attendance records deleted if empty.'}, status=204)