from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
import math
import logging
from attendance_management.models import AttendanceRecord, Schedule, Branch, Student
from django.shortcuts import get_object_or_404
from users.models import CustomUser
from django.utils import timezone
from core.permissions import IsSupervisorOrAboveUser  # Changed from relative to absolute import

logger = logging.getLogger(__name__)

class AttendanceViewSet(viewsets.ViewSet):
    """
    API endpoints for attendance validation and management.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['POST'], url_path='check-in')
    def check_in(self, request):
        """
        Check in a student by validating their location against the geofencing area.
        
        Request body should contain:
        - user_id: ID of the user
        - uuid: UUID for the student's phone
        - latitude: User's current latitude
        - longitude: User's current longitude
        """
        # Extract data from request
        user_id = request.data.get('user_id')
        uuid = request.data.get('uuid')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        # Validate request data
        if not all([user_id, uuid, latitude, longitude]):
            return Response(
                {"error": "Missing required fields. Please provide user_id, uuid, latitude, and longitude."},
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
        
        # Get user
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Get student record for this user
        try:
            student = Student.objects.get(user=user)
            
            # Check if the student has already checked in
            if student.is_checked_in:
                logger.warning(f"Student {student.user.email} attempted to check in again while already checked in")
                return Response({
                    "status": "error",
                    "message": "You have already checked in.",
                    "error_code": "already_checked_in"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if the student has a UUID
            if student.phone_uuid and student.phone_uuid != uuid:
                # Student has a different UUID - return error message
                logger.warning(f"UUID mismatch for student {student.user.email}: received {uuid}, stored {student.phone_uuid}")
                return Response({
                    "status": "error",
                    "message": "Incorrect device UUID. Please use the same device you used during registration or contact an administrator.",
                    "error_code": "uuid_mismatch"
                }, status=status.HTTP_400_BAD_REQUEST)
            elif not student.phone_uuid:
                # Student exists but has no UUID, so update it
                student.phone_uuid = uuid
                student.save(update_fields=['phone_uuid'])
                logger.info(f"Set phone UUID for student {student.user.email} to {uuid}")
        except Student.DoesNotExist:
            return Response(
                {"error": "No student record found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get latest attendance record for this student - using check_in_time instead of timestamp
        attendance_record = AttendanceRecord.objects.filter(student=student).order_by('-check_in_time').first()
        
        # If no attendance record exists with check_in_time, try to get the latest by ID
        if not attendance_record:
            attendance_record = AttendanceRecord.objects.filter(student=student).order_by('-id').first()
            
        if not attendance_record:
            return Response(
                {"error": "No attendance record found for this student."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get schedule and branch
        schedule = attendance_record.schedule
        branch = schedule.custom_branch
        
        # Calculate distance between user and branch coordinates
        branch_latitude = branch.latitude
        branch_longitude = branch.longitude
        geofence_radius = branch.radius  # in meters
        
        distance = self._calculate_distance(latitude, longitude, branch_latitude, branch_longitude)
        
        # Check if user is within the geofence
        if distance <= geofence_radius:
            # User is within the geofence - update check-in time and mark student as checked in
            current_time = timezone.now()
            
            # Update check_in_time if not already set
            if not attendance_record.check_in_time:
                attendance_record.check_in_time = current_time
                attendance_record.save(update_fields=['check_in_time'])
                logger.info(f"Check-in time set for student {student.user.email}")
            
            # Mark student as checked in
            student.is_checked_in = True
            student.save(update_fields=['is_checked_in'])
            logger.info(f"Student {student.user.email} marked as checked in")
            
            logger.info(f"Student {student.user.email} successfully validated attendance at {branch.name}")
            
            return Response({
                "status": "success",
                "message": "Attendance validated successfully",
                "distance": distance,
                "geofence_radius": geofence_radius,
                "check_in_time": attendance_record.check_in_time
            })
        else:
            # User is outside the geofence
            logger.warning(f"Student {student.user.email} failed location validation: distance {distance}m exceeds radius {geofence_radius}m")
            
            return Response({
                "status": "fail",
                "message": "You are outside the allowed geofence area",
                "distance": distance,
                "geofence_radius": geofence_radius
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], url_path='check-out')
    def check_out(self, request):
        """
        Check out a student by validating their location against the geofencing area.
        
        Request body should contain:
        - user_id: ID of the user
        - uuid: UUID for the student's phone
        - latitude: User's current latitude
        - longitude: User's current longitude
        """
        # Extract data from request
        user_id = request.data.get('user_id')
        uuid = request.data.get('uuid')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        # Validate request data
        if not all([user_id, uuid, latitude, longitude]):
            return Response(
                {"error": "Missing required fields. Please provide user_id, uuid, latitude, and longitude."},
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
        
        # Get user
        user = get_object_or_404(CustomUser, id=user_id)
        
        # Get student record for this user
        try:
            student = Student.objects.get(user=user)
            
            # Check if the student is checked in (can't check out if not checked in)
            if not student.is_checked_in:
                logger.warning(f"Student {student.user.email} attempted to check out but hasn't checked in")
                return Response({
                    "status": "error",
                    "message": "You haven't checked in yet. Please check in first.",
                    "error_code": "not_checked_in"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check if the student has a UUID
            if student.phone_uuid and student.phone_uuid != uuid:
                # Student has a different UUID - return error message
                logger.warning(f"UUID mismatch for student {student.user.email}: received {uuid}, stored {student.phone_uuid}")
                return Response({
                    "status": "error",
                    "message": "Incorrect device UUID. Please use the same device you used during registration or contact an administrator.",
                    "error_code": "uuid_mismatch"
                }, status=status.HTTP_400_BAD_REQUEST)
        except Student.DoesNotExist:
            return Response(
                {"error": "No student record found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get latest attendance record for this student that has a check-in but no check-out
        attendance_record = AttendanceRecord.objects.filter(
            student=student, 
            check_in_time__isnull=False,
            check_out_time__isnull=True
        ).order_by('-check_in_time').first()
        
        if not attendance_record:
            # Try to get the latest attendance record by ID if no appropriate record is found
            attendance_record = AttendanceRecord.objects.filter(student=student).order_by('-id').first()
            
            if not attendance_record:
                return Response(
                    {"error": "No attendance record found for this student."},
                    status=status.HTTP_404_NOT_FOUND
                )
            if student.is_checked_in==False:
                return Response({
                    "status": "error",
                    "message": "You have already checked out for this session.",
                    "error_code": "already_checked_out"
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get schedule and branch
        schedule = attendance_record.schedule
        branch = schedule.custom_branch
        
        # Calculate distance between user and branch coordinates
        branch_latitude = branch.latitude
        branch_longitude = branch.longitude
        geofence_radius = branch.radius  # in meters
        
        distance = self._calculate_distance(latitude, longitude, branch_latitude, branch_longitude)
        
        # Check if user is within the geofence
        if distance <= geofence_radius:
            # User is within the geofence - set check-out time and update student status
            current_time = timezone.now()
            
            # Update check_out_time
            attendance_record.check_out_time = current_time
            attendance_record.save()
            logger.info(f"Check-out time set for student {student.user.email}")
            
            # Explicitly set and save student's check-in status to False
            Student.objects.filter(id=student.id).update(is_checked_in=False)
            logger.info(f"Student {student.user.email} marked as checked out using queryset update")
            
            # Calculate duration of attendance
            time_difference = attendance_record.check_out_time - attendance_record.check_in_time
            hours = time_difference.total_seconds() / 3600
            
            # Refresh student from database to confirm is_checked_in is False
            student.refresh_from_db()
            logger.info(f"After checkout, student.is_checked_in = {student.is_checked_in}")
            
            logger.info(f"Student {student.user.email} successfully checked out at {branch.name}")
            
            return Response({
                "status": "success",
                "message": "Check-out successful",
                "distance": distance,
                "geofence_radius": geofence_radius,
                "check_in_time": attendance_record.check_in_time,
                "check_out_time": attendance_record.check_out_time,
                "attendance_duration_hours": round(hours, 2),
                "is_checked_in": student.is_checked_in  # Include in response to confirm status
            })
        else:
            # User is outside the geofence
            logger.warning(f"Student {student.user.email} failed location validation: distance {distance}m exceeds radius {geofence_radius}m")
            
            return Response({
                "status": "fail",
                "message": "You are outside the allowed geofence area",
                "distance": distance,
                "geofence_radius": geofence_radius
            }, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'], url_path='reset-check-ins', permission_classes=[IsSupervisorOrAboveUser])
    def reset_check_ins(self, request):
        """
        Reset the check-in status for all students.
        Only accessible by admin users.
        """
        # Reset all students' is_checked_in to False
        count = Student.objects.filter(is_checked_in=True).update(is_checked_in=False)
        
        logger.info(f"Reset check-in status for {count} students")
        
        return Response({
            "status": "success",
            "message": f"Successfully reset check-in status for {count} students."
        })

    @action(detail=False, methods=['POST'], url_path='reset-student', permission_classes=[IsSupervisorOrAboveUser])
    def reset_student(self, request):
        """
        Reset a specific student's check-in status.
        Requires user_id in the request body.
        """
        user_id = request.data.get('user_id')
        
        if not user_id:
            return Response({
                "error": "Missing required field: user_id"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            student = Student.objects.get(user_id=user_id)
            was_checked_in = student.is_checked_in
            student.is_checked_in = False
            student.save(update_fields=['is_checked_in'])
            
            logger.info(f"Reset check-in status for student {student.user.email} from {was_checked_in} to False")
            
            return Response({
                "status": "success",
                "message": f"Successfully reset check-in status for student {student.user.email}",
                "previous_status": was_checked_in,
                "current_status": student.is_checked_in
            })
        except Student.DoesNotExist:
            return Response({
                "error": "Student not found"
            }, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['GET'], url_path='status')
    def is_checked_in(self, request):
        """
        Return the is_checked_in status of the logged-in student.
        """
        try:
            # Get the logged-in user's student profile
            student = Student.objects.get(user=request.user)
            return Response({
                "status": "success",
                "is_checked_in": student.is_checked_in
            })
        except Student.DoesNotExist:
            return Response({
                "status": "error",
                "message": "No student record found for the logged-in user."
            }, status=status.HTTP_404_NOT_FOUND)

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
