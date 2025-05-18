from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime  # Import parse_datetime
from ..models import Event, EventAttendanceRecord, Student, Guest, Schedule, Track, Session, Branch  # Import Branch
from ..serializers import EventSerializer, EventAttendanceRecordSerializer, EventSessionSerializer
from core.permissions import IsCoordinatorOrAboveUser, IsStudentOrAboveUser, IsGuestOrAboveUser
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

from attendance_management.models import Event
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

                # 4. Create sessions (optimized with bulk_create)
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
        user = self.request.user
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
            queryset = queryset.filter(audience_type__in=['guests_only', 'both'])

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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

    @action(detail=True, methods=['POST'],url_path='register', permission_classes=[IsStudentOrAboveUser])
    def register(self, request, pk=None):
        """
        Register for an event.
        - Students can register if their track is eligible
        - Guests can register for guest-allowed events
        """
        try:
            event = self.get_object()
            user = request.user

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

            else:
                return Response(
                    {"error": "Invalid user type"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                EventAttendanceRecordSerializer(attendance_record).data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )