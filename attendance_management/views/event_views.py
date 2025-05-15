import math
import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q

from attendance_management.models import (
    EventAttendanceRecord, Schedule, Student, Guest, Event
)
from attendance_management.serializers import EventAttendanceRecordSerializer
from users.models import CustomUser

logger = logging.getLogger(__name__)

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