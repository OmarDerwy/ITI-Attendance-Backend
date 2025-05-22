from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
import math
import logging
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.utils.dateparse import parse_datetime  # Import parse_datetime
from ..models import Event, EventAttendanceRecord, Student, Guest, Schedule, Track, Session, Branch  # Import Branch
from ..serializers import EventSerializer, EventAttendanceRecordSerializer, EventSessionSerializer
from core.permissions import IsCoordinatorOrAboveUser, IsStudentOrAboveUser, IsGuestOrAboveUser
from django.db.models import Q, Count, Min

logger = logging.getLogger(__name__)

from attendance_management.models import Event

class EventAttendancePagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 100
class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    
    def get_permissions(self):
        """
        Define permission classes based on action.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsCoordinatorOrAboveUser]
        else:
            permission_classes = [IsGuestOrAboveUser]
        return [permission() for permission in permission_classes]

    def create(self, request, *args, **kwargs):
        """Create an event with its associated schedule and sessions"""
        try:
            with transaction.atomic():
                # 1. Validate required fields
                if not all([
                    request.data.get('title'),
                    request.data.get('event_date')
                ]):
                    return Response(
                        {"error": "Title and event_date are required"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # 2. Create event
                event_data = {
                    'description': request.data.get('description'),
                    'audience_type': request.data.get('audience_type', 'students_only'),
                    'is_mandatory': request.data.get('is_mandatory', False),
                }
                event = Event.objects.create(**event_data)

                # 3. Create schedule
                schedule_date = parse_datetime(request.data.get('event_date')).date()
                branch = request.user.coordinator.branch
                schedule = Schedule.objects.create(
                    name=request.data.get('title'),
                    created_at=schedule_date,
                    custom_branch=branch,
                    event=event,
                    is_shared=True
                )

                # 4. Create sessions 
                sessions_data = request.data.get('sessions', [])
                sessions_to_create = []
                for session_data in sessions_data:
                    try:
                        sessions_to_create.append(
                            Session(
                                schedule=schedule,
                                title=session_data['title'],
                                instructor=session_data.get('speaker'),
                                start_time=parse_datetime(session_data['start_time']),
                                end_time=parse_datetime(session_data['end_time']),
                                session_type=session_data.get('session_type', 'offline'),
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error preparing session: {session_data}. Error: {str(e)}")
                        raise  # Re-raise to rollback

                Session.objects.bulk_create(sessions_to_create)

                # 5. Add target tracks if provided
                target_track_ids = request.data.get('target_track_ids', [])
                if target_track_ids:
                    tracks = Track.objects.filter(
                        id__in=target_track_ids,
                        is_active=True,
                        default_branch=request.user.coordinator.branch
                    )
                    event.target_tracks.set(tracks)

                # 6. Auto-register students if mandatory
                if event.is_mandatory and event.target_tracks.exists():
                    self._auto_register_students(event)

                # 7. Return serialized event (consider a simpler response)
                return Response(
                    self.get_serializer(event).data,
                    status=status.HTTP_201_CREATED
                )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


    def get_queryset(self):
        base_queryset = Event.objects.all()

        return base_queryset.prefetch_related(
            'schedule__sessions',
            'target_tracks',
            'schedule__event_attendance_records',
            'schedule__event_attendance_records__student__user',
            'schedule__event_attendance_records__guest',
            'schedule__event_attendance_records__schedule',
        )

    def list(self, request, *args, **kwargs):
        user = request.user
        queryset = self.get_queryset()

        if user.groups.filter(name='coordinator').exists():
            queryset = queryset.filter(schedule__custom_branch=user.coordinator.branch)
        elif user.groups.filter(name='admin').exists():
            queryset = queryset.all()
        elif user.groups.filter(name='supervisor').exists():
            supervisor_tracks = Track.objects.filter(supervisor=user)
            queryset = queryset.filter(target_tracks__in=supervisor_tracks).distinct()
        elif user.groups.filter(name='branch-manager').exists():
            queryset = queryset.filter(schedule__custom_branch=user.branch_manager.branch)
        elif user.groups.filter(name='student').exists():
            student = user.student_profile
            queryset = queryset.filter(
                Q(audience_type__in=['students_only', 'both']),
                Q(target_tracks=student.track) | Q(target_tracks__isnull=True)
            ).distinct()

        # For guests, show only guest-allowed events
        elif hasattr(user, 'guest_profile'):
            queryset = queryset.filter(
                audience_type__in=['guests_only', 'both'],
                schedule__event_attendance_records__guest__user=user
            ).distinct()

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                event = self.get_object()

                # 1. Update event fields
                event.description = request.data.get('description', event.description)
                event.audience_type = request.data.get('audience_type', event.audience_type)
                event.is_mandatory = request.data.get('is_mandatory', event.is_mandatory)
                event.save()

                # 2. Update schedule
                schedule = event.schedule
                if 'event_date' in request.data:
                    schedule.created_at = parse_datetime(request.data.get('event_date')).date()
                    schedule.save()

                # 3. Update sessions
                sessions_data = request.data.get('sessions', [])
                if sessions_data:
                    # Delete old sessions
                    schedule.sessions.all().delete()

                    # Create new sessions
                    new_sessions = []
                    for session_data in sessions_data:
                        new_sessions.append(
                            Session(
                                schedule=schedule,
                                title=session_data['title'],
                                instructor=session_data.get('speaker'),
                                start_time=parse_datetime(session_data['start_time']),
                                end_time=parse_datetime(session_data['end_time']),
                                session_type=session_data.get('session_type', 'offline'),
                            )
                        )
                    Session.objects.bulk_create(new_sessions)

                # 4. Update target tracks and handle auto-registration
                old_target_tracks = set(event.target_tracks.all())
                new_target_track_ids = request.data.get('target_track_ids', [])
                new_tracks = Track.objects.filter(
                    id__in=new_target_track_ids,
                    is_active=True,
                    default_branch=request.user.coordinator.branch
                )
                new_target_tracks = set(new_tracks)

                if old_target_tracks != new_target_tracks:
                    # Delete existing attendance records for the event
                    EventAttendanceRecord.objects.filter(schedule=schedule).delete()

                    event.target_tracks.set(new_tracks)  # Update target tracks

                    # Auto-register students if mandatory and target tracks exist
                    if event.is_mandatory and event.target_tracks.exists():
                        self._auto_register_students(event)
                    elif event.is_mandatory and not event.target_tracks.exists() and event.audience_type in ['students_only', 'both']:
                        # Auto-register all active students if mandatory and no target tracks
                        students = Student.objects.filter(user__is_active=True, track__is_active=True)
                        EventAttendanceRecord.objects.bulk_create([
                            EventAttendanceRecord(schedule=schedule, student=student, status='registered')
                            for student in students
                        ])

                return Response(self.get_serializer(event).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


    def _auto_register_students(self, event):
        """Helper method to automatically register students for mandatory events"""
        students = Student.objects.filter(
            track__in=event.target_tracks.all(),
            user__is_active=True,
            track__is_active=True
        )

        # Use a generator expression with bulk_create
        EventAttendanceRecord.objects.bulk_create(
            EventAttendanceRecord(
                schedule=event.schedule,
                student=student,
                status='registered'
            ) for student in students
        )
    
    @action(detail=False, methods=['GET'], url_path='events-for-registration')
    def get_events_for_registration(self, request, pk=None):
        '''
        GUEST ONLY
        get events that the logged guest has no eventRecordAttendance for.
        '''
        try:
            user = request.user
            if not hasattr(user, 'guest_profile'):
                return Response(
                    {"error": "Only guests can access this endpoint"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Get today's date
            now = timezone.localtime()

            # Annotate each event with the earliest session start time
            events = Event.objects.filter(
                Q(audience_type='guests_only') | Q(audience_type='both'),
            ).annotate(
                earliest_session_start=Min('schedule__sessions__start_time')
            ).filter(
                earliest_session_start__gte=now
            ).exclude(
                schedule__event_attendance_records__guest__user=user
            ).distinct()

            serializer = self.get_serializer(events, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['POST'], url_path='register', permission_classes=[IsStudentOrAboveUser])
    def register(self, request, pk=None):
        """
        Register for an event.
        - Students can register if their track is eligible
        - Guests can register for guest-allowed events
        """
        try:
            event = self.get_object()
            user = request.user

            #check if event is in the future
            if event.schedule.created_at < timezone.now().date():
                return Response(
                    {"error": "Cannot register for past events"},
                    status=status.HTTP_400_BAD_REQUEST
                )


            # Check if already registered
            existing_registration = EventAttendanceRecord.objects.filter(
                Q(student__user=user) | Q(guest__user=user),
                schedule=event.schedule
            ).exists()

            if existing_registration:
                return Response(
                    {"error": "Already registered for this event"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Handle student registration
            if hasattr(user, 'student_profile'):
                student = user.student_profile

                # Validate student can register
                if event.audience_type == 'guests_only':
                    return Response(
                        {"error": "This event is for guests only"},
                        status=status.HTTP_403_FORBIDDEN
                    )

                if event.target_tracks.exists() and student.track not in event.target_tracks.all():
                    return Response(
                        {"error": "Your track is not eligible for this event"},
                        status=status.HTTP_403_FORBIDDEN
                    )

                attendance_record = EventAttendanceRecord.objects.create(
                    schedule=event.schedule,
                    student=student,
                    status='registered'
                )
                event.registered_students += 1  # Increment student count

            # Handle guest registration
            elif hasattr(user, 'guest_profile'):
                if event.audience_type == 'students_only':
                    return Response(
                        {"error": "This event is for students only"},
                        status=status.HTTP_403_FORBIDDEN
                    )

                attendance_record = EventAttendanceRecord.objects.create(
                    schedule=event.schedule,
                    guest=user.guest_profile,
                    status='registered'
                )
                event.registered_guests += 1  # Increment guest count

            else:
                return Response(
                    {"error": "Invalid user type"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            event.save()  # Save the updated event

            return Response(
                EventAttendanceRecordSerializer(attendance_record).data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['GET'], url_path='guest_details')
    def get_guest_details(self, request, pk=None):
        """
        Retrieve guest details for a specific event, separated into enrolled and attended.
        """
        try:
            event = self.get_object()

            # Get enrolled guests
            enrolled_guests = EventAttendanceRecord.objects.filter(
                schedule=event.schedule,
                guest__isnull=False,
            ).select_related('guest__user')  # Optimize query

            # Get attended guests
            attended_guests = EventAttendanceRecord.objects.filter(
                schedule=event.schedule,
                guest__isnull=False,
                status='attended'
            ).select_related('guest__user')  # Optimize query

            # Serialize the data
            enrolled_serializer = EventAttendanceRecordSerializer(enrolled_guests, many=True)
            attended_serializer = EventAttendanceRecordSerializer(attended_guests, many=True)

            data = {
                'enrolled': enrolled_serializer.data,
                'attended': attended_serializer.data,
            }

            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['GET'], url_path='attendance_stats')
    def get_attendance_stats(self, request):#this method for guests only
        """
        Retrieve attendance statistics for all events.
        """
        try:
            events = Event.objects.all().order_by('-schedule__created_at')  
            paginator = EventAttendancePagination()
            page = paginator.paginate_queryset(events, request) 
            data = []
            for event in events:
                event_data = {
                    'id': event.id,
                    'title': event.title,  
                    'date': event.schedule.created_at if hasattr(event, 'schedule') and event.schedule else None,  
                    'attended': event.attended_guests,
                    'enrolled': event.registered_guests,
                }
                data.append(event_data)
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventAttendanceViewSet(viewsets.ViewSet):
    """
    API endpoints for event attendance management.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['POST'], url_path='check-in')
    def event_check_in(self, request):
        """
        Check in a student or guest for an event by validating their location against the geofencing area.
        Uses the currently authenticated user and finds today's event schedules.
        
        Request body should contain:
        - latitude: User's current latitude
        - longitude: User's current longitude
        """
        # Get current authenticated user
        user = request.user
        
        # Extract data from request
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        # Validate request data
        if not all([latitude, longitude]):
            return Response(
                {"error": "Missing required fields. Please provide latitude and longitude."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Convert latitude and longitude to float
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            return Response(
                {"error": "Invalid latitude or longitude format. Please provide valid decimal numbers."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user is active
        if not user.is_active:
            return Response({
                "status": "error", 
                "message": "Your account is not active. Please contact an administrator.",
                "error_code": "account_not_active"
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get today's date for finding today's event schedules
        today = timezone.localdate()
        
        # Find event schedules for today
        today_event_schedules = Schedule.objects.filter(
            created_at=today,
            event__isnull=False  # Must have an associated event
        )
        
        if not today_event_schedules.exists():
            return Response({
                "status": "error",
                "message": "No events are scheduled for today.",
                "error_code": "no_events_today"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Try to determine if the user is a student or guest
        student = None
        guest = None
        attendee_type = None
        
        try:
            student = Student.objects.get(user=user)
            attendee_type = 'student'
        except Student.DoesNotExist:
            try:
                guest = Guest.objects.get(user=user)
                attendee_type = 'guest'
            except Guest.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "No student or guest profile found for this user.",
                    "error_code": "profile_not_found"
                }, status=status.HTTP_404_NOT_FOUND)
        
        # Find the event attendance record for this user
        attendance_record = None
        matching_schedule = None
        
        if attendee_type == 'student':            # For students, find schedules they can attend based on track and audience type
            valid_schedules = today_event_schedules.filter(
                Q(event__audience_type__in=['students_only', 'both']),
                Q(event__target_tracks__isnull=True) | Q(event__target_tracks=student.track)
            )
            
            if not valid_schedules.exists():
                return Response({
                    "status": "error",
                    "message": "No events available for your track today.",
                    "error_code": "no_events_for_track"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Look for an existing attendance record
            for schedule in valid_schedules:
                try:
                    attendance_record = EventAttendanceRecord.objects.get(
                        schedule=schedule,
                        student=student
                    )
                    matching_schedule = schedule
                    break
                except EventAttendanceRecord.DoesNotExist:
                    continue
            
        else:  # Guest
            # For guests, find schedules they can attend based on audience type
            valid_schedules = today_event_schedules.filter(
                event__audience_type__in=['guests_only', 'both']
            )
            
            if not valid_schedules.exists():
                return Response({
                    "status": "error",
                    "message": "No events available for guests today.",
                    "error_code": "no_events_for_guests"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Look for an existing attendance record
            for schedule in valid_schedules:
                try:
                    attendance_record = EventAttendanceRecord.objects.get(
                        schedule=schedule,
                        guest=guest
                    )
                    matching_schedule = schedule
                    break
                except EventAttendanceRecord.DoesNotExist:
                    continue
        
        if not attendance_record:
            return Response({
                "status": "error",
                "message": "No attendance record found for any of today's events. Please register for an event first.",
                "error_code": "attendance_record_not_found"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if already checked in
        if attendance_record.check_in_time:
            return Response({
                "status": "error",
                "message": "You have already checked in for today's event.",
                "error_code": "already_checked_in"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get branch for geofence validation
        branch = matching_schedule.custom_branch
        
        # Calculate distance between user and branch coordinates
        branch_latitude = branch.latitude
        branch_longitude = branch.longitude
        geofence_radius = branch.radius  # in meters
        
        distance = self._calculate_distance(latitude, longitude, branch_latitude, branch_longitude)
        
        # Check if user is within the geofence
        if distance <= geofence_radius:
            # User is within the geofence - update check-in time
            current_time = timezone.localtime()
            
            # Update check_in_time and status
            attendance_record.check_in_time = current_time
            attendance_record.status = 'attended'
            attendance_record.save(update_fields=['check_in_time', 'status'])

            # Increment attended counts on the Event model
            event = matching_schedule.event  
            if attendee_type == 'student':
                event.attended_students += 1
            else:
                event.attended_guests += 1
            event.save()  
            
            logger.info(f"Event check-in recorded for {attendee_type} {user.email} at {branch.name}")
            
            return Response({
                "status": "success",
                "message": "Event check-in recorded successfully",
                "distance": distance,
                "geofence_radius": geofence_radius,
                "check_in_time": attendance_record.check_in_time,
                "event_name": matching_schedule.name
            })
        else:
            # User is outside the geofence
            logger.warning(f"{attendee_type.capitalize()} {user.email} failed location validation: distance {distance}m exceeds radius {geofence_radius}m")
            
            return Response({
                "status": "fail",
                "message": "You are outside the allowed geofence area",
                "distance": distance,
                "geofence_radius": geofence_radius
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate the distance between two coordinates using the Haversine formula.
        Returns distance in meters.
        """
        # Earth's radius in meters
        R = 6371000
        
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Differences
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # Haversine formula
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        
        return distance