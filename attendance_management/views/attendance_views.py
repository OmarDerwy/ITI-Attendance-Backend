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
from ..models import PermissionRequest, Track
from ..serializers import AttendanceRecordSerializer, AttendanceRecordSerializerForStudents
from django.db.models import Count, Q
from datetime import timedelta
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from collections import OrderedDict
import calendar
from rest_framework import status


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

            # check if student is active
            if not student.user.is_active:
                logger.warning(f"Student {student.user.email} is not active")
                return Response({
                    "status": "error",
                    "message": "Your account is not active. Please contact an administrator.",
                    "error_code": "account_not_active"
                }, status=status.HTTP_403_FORBIDDEN)
            

            
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
        
        # Get today's date
        today = timezone.now().date()
        
        # Find a schedule for today and get corresponding attendance record
        try:
            # Find schedules for the student's track that are for today
            schedule = Schedule.objects.filter(
                track=student.track,
                created_at=today
            ).first()
            
            if not schedule:
                return Response({
                    "status": "error",
                    "message": "No schedule found for today.",
                    "error_code": "no_schedule_today"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Find attendance record for this student and schedule
            attendance_record = AttendanceRecord.objects.filter(
                student=student,
                schedule=schedule
            ).first()
            
            if not attendance_record:
                # Create a new attendance record if one doesn't exist
                attendance_record = AttendanceRecord.objects.create(
                    student=student,
                    schedule=schedule
                )
                logger.info(f"Created new attendance record for {student.user.email} for today's schedule")
        except Exception as e:
            logger.error(f"Error finding attendance record: {str(e)}")
            return Response({
                "status": "error",
                "message": f"Error finding attendance record: {str(e)}",
                "error_code": "attendance_record_error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if the student has already checked in
        if attendance_record.check_in_time:
            logger.warning(f"Student {student.user.email} have already checked in for today's session")
            return Response({
                "status": "error",
                "message": "You have already checked in for today's session.",
                "error_code": "already_checked_in"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        
        # Get branch for geofence validation
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
                "check_in_time": attendance_record.check_in_time,
                "schedule_name": schedule.name
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
            return Response({
                "error": "Missing required fields. Please provide user_id, uuid, latitude, and longitude."
            }, status=status.HTTP_400_BAD_REQUEST)
        
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

            # check if student is active
            if not student.user.is_active:
                logger.warning(f"Student {student.user.email} is not active")
                return Response({
                    "status": "error",
                    "message": "Your account is not active. Please contact an administrator.",
                    "error_code": "account_not_active"
                }, status=status.HTTP_403_FORBIDDEN)
            
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
        
        # Get today's date
        today = timezone.now().date()
        
        # Find a schedule for today and get corresponding attendance record
        try:
            # Find schedules for the student's track that are for today
            schedule = Schedule.objects.filter(
                track=student.track,
                created_at=today
            ).first()
            
            if not schedule:
                return Response({
                    "status": "error",
                    "message": "No schedule found for today.",
                    "error_code": "no_schedule_today"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Find attendance record for this student and schedule with check-in
            attendance_record = AttendanceRecord.objects.filter(
                student=student,
                schedule=schedule,
                # check_in_time__isnull=False  # Must have checked in first
            ).first()
            
            if not attendance_record:
                return Response({
                    "status": "error",
                    "message": "No checked-in attendance record found for today.",
                    "error_code": "no_checkin_record"
                }, status=status.HTTP_404_NOT_FOUND)
                
            # Check if already checked out
            if attendance_record.check_out_time:
                return Response({
                    "status": "error",
                    "message": "You have already checked out for this session.",
                    "error_code": "already_checked_out"
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error finding attendance record: {str(e)}")
            return Response({
                "status": "error",
                "message": f"Error finding attendance record: {str(e)}",
                "error_code": "attendance_record_error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Get branch for geofence validation
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
            attendance_record.save(update_fields=['check_out_time'])
            logger.info(f"Check-out time set for student {student.user.email}")
            
            # Explicitly set and save student's check-in status to False
            student.is_checked_in = False
            student.save(update_fields=['is_checked_in'])
            logger.info(f"Student {student.user.email} marked as checked out")
            
            # Calculate duration of attendance
            time_difference = attendance_record.check_out_time - attendance_record.check_in_time
            hours = time_difference.total_seconds() / 3600
            
            logger.info(f"Student {student.user.email} successfully checked out at {branch.name}")
            
            return Response({
                "status": "success",
                "message": "Check-out successful", 
                "distance": distance,
                "geofence_radius": geofence_radius,
                "check_in_time": attendance_record.check_in_time,
                "check_out_time": attendance_record.check_out_time,
                "attendance_duration_hours": round(hours, 2),
                "is_checked_in": False,
                "schedule_name": schedule.name
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

    @action(detail=False, methods=['GET'], url_path='supervisor-attendance')
    def get_supervisor_attendance(self, request):
        """
        Get attendance records of students whose tracks are managed by the logged-in supervisor
        for a specific date (defaults to today if not provided) and optionally for a specific track.
        """
        try:
            supervisor = request.user
            if not Track.objects.filter(supervisor=supervisor).exists():
                return Response({
                    "status": "error",
                    "message": "You are not assigned as a supervisor to any track."
                }, status=status.HTTP_403_FORBIDDEN)

            date_str = request.query_params.get('date')
            if date_str:
                try:
                    date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    return Response({
                        "status": "error",
                        "message": "Invalid date format. Please use YYYY-MM-DD."
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                date = timezone.now().date()

            track_id = request.query_params.get('track_id')
            tracks = Track.objects.filter(supervisor=supervisor)
            if track_id:
                tracks = tracks.filter(id=track_id)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "The specified track does not exist or is not managed by you."
                    }, status=status.HTTP_404_NOT_FOUND)

            attendance_records = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                schedule__created_at=date 
            )
            serializer = AttendanceRecordSerializer(attendance_records, many=True)

            return Response(serializer.data, status=status.HTTP_200_OK)


        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['GET'], url_path='attendance-percentage/today')
    def get_todays_attendance_percentage(self, request):
        """
        Get today's attendance percentage for the tracks managed by the logged-in supervisor.
        """
        try:
            supervisor = request.user
            if not Track.objects.filter(supervisor=supervisor).exists():
                return Response({
                    "status": "error",
                    "message": "You are not assigned as a supervisor to any track."
                }, status=status.HTTP_403_FORBIDDEN)

            date = timezone.now().date()
            tracks = Track.objects.filter(supervisor=supervisor)

            total_students = Student.objects.filter(track__in=tracks).count()
            attended_students = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                schedule__created_at=date,
                check_in_time__isnull=False
            ).count()

            attendance_percentage = (attended_students / total_students) * 100 if total_students > 0 else 0

            return Response({
                "date": date,
                "total_students": total_students,
                "attended_students": attended_students,
                "attendance_percentage": round(attendance_percentage, 2)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#TODO [AP-75]: fix bug in this function
    @action(detail=False, methods=['GET'], url_path='attendance-percentage/weekly')
    def get_weekly_attendance_percentage(self, request):
        """
        Get weekly attendance percentage for the tracks managed by the logged-in supervisor.
        """
        try:
            supervisor = request.user
            if not Track.objects.filter(supervisor=supervisor).exists():
                return Response({
                    "status": "error",
                    "message": "You are not assigned as a supervisor to any track."
                }, status=status.HTTP_403_FORBIDDEN)

            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=7)
            tracks = Track.objects.filter(supervisor=supervisor)

            total_students = Student.objects.filter(track__in=tracks).count()
            # Get schedules in the past week
            schedules = Schedule.objects.filter(
                track__in=tracks,
                created_at__range=(start_date, end_date)
            )
            num_schedules = schedules.count()

            # Calculate expected attendance records
            expected_attendance_count = total_students * num_schedules

            # Count actual attendance records with check-ins
            actual_attendance_count = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                schedule__in=schedules,
                check_in_time__isnull=False
            ).count()

            attendance_percentage = (
                (actual_attendance_count / expected_attendance_count) * 100
                if expected_attendance_count > 0 else 0
)


            return Response({
                "start_date": start_date,
                "end_date": end_date,
                "total_students": total_students,
                "number_of_schedules": num_schedules,
                "expected_attendance_count": expected_attendance_count,
                "actual_attendance_count": actual_attendance_count,
                "attendance_percentage": round(attendance_percentage, 2)
            }, status=status.HTTP_200_OK)


        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['GET'], url_path='attendance-trends')
    def get_attendance_trends(self, request):
        """
        Get attendance trends (daily, weekly, and monthly) for the tracks managed by the logged-in supervisor.
        Optionally filter by a specific track using the 'track_id' query parameter.
        """
        try:
            supervisor = request.user
            if not Track.objects.filter(supervisor=supervisor).exists():
                return Response({
                    "status": "error",
                    "message": "You are not assigned as a supervisor to any track."
                }, status=status.HTTP_403_FORBIDDEN)

            # Get the track_id from query parameters
            track_id = request.query_params.get('track_id')
            tracks = Track.objects.filter(supervisor=supervisor)

            if track_id:
                tracks = tracks.filter(id=track_id)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "The specified track does not exist or is not managed by you."
                    }, status=status.HTTP_404_NOT_FOUND)

            # Daily trends
            daily_trends = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                check_in_time__isnull=False
            ).annotate(date=TruncDate('schedule__created_at')).values('date').annotate(
                attended=Count('id')
            ).order_by('date')

            # Weekly trends
            weekly_trends = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                check_in_time__isnull=False
            ).annotate(week=TruncWeek('schedule__created_at')).values('week').annotate(
                attended=Count('id')
            ).order_by('week')

            # Monthly trends
            monthly_trends = AttendanceRecord.objects.filter(
                student__track__in=tracks,
                check_in_time__isnull=False
            ).annotate(month=TruncMonth('schedule__created_at')).values('month').annotate(
                attended=Count('id')
            ).order_by('month')

            return Response({
                "daily_trends": list(daily_trends),
                "weekly_trends": list(weekly_trends),
                "monthly_trends": list(monthly_trends)
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    @action(detail=True, methods=['PATCH'], url_path='reset-attendance', permission_classes=[IsSupervisorOrAboveUser])
    def reset_attendance(self, request, pk):
        """
        Reset a specific attendance record by setting check_in_time and check_out_time to null.
        Requires attendance_record_id in the request body.
        """
        
        try:
            attendance_record = get_object_or_404(AttendanceRecord, id=pk)
            # Store previous values for logging
            previous_check_in = attendance_record.check_in_time
            previous_check_out = attendance_record.check_out_time
            
            # Reset check-in and check-out times
            attendance_record.check_in_time = None
            attendance_record.check_out_time = None
            attendance_record.save(update_fields=['check_in_time', 'check_out_time'])

            # get permission request if exists
            permission_request = PermissionRequest.objects.filter(student=attendance_record.student, schedule=attendance_record.schedule).first()
            if permission_request:
                permission_request.status = 'rejected'
                permission_request.save(update_fields=['status'])
            
            # Also reset the student's is_checked_in status if needed
            student = attendance_record.student
            if student.is_checked_in:
                student.is_checked_in = False
                student.save(update_fields=['is_checked_in'])
            
            logger.info(f"Reset attendance record {pk} for student {student.user.email}")
            
            return Response({
                "status": "success",
                "message": f"Successfully reset attendance record for student {student.user.email}",
                "previous_check_in": previous_check_in,
                "previous_check_out": previous_check_out,
                "current_check_in": attendance_record.check_in_time,
                "current_check_out": attendance_record.check_out_time,
                "is_checked_in": student.is_checked_in,
                "adjusted_time": None
            })
        except AttendanceRecord.DoesNotExist:
            return Response({
                "error": f"Attendance record with ID {pk} not found"
            }, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['PATCH'], url_path='manual-attend', permission_classes=[IsSupervisorOrAboveUser])
    def manual_attend(self, request, pk):
        """
        Manually record attendance for a student using the first and last session times of their schedule.
        Request body should contain:
        - attendance_record_id: ID of the attendance record to update
        """
        
        try:
            payload = {}
            # Get the attendance record
            attendance_record = get_object_or_404(AttendanceRecord, id=pk)
            schedule = attendance_record.schedule
            student = attendance_record.student
            
            # Get the schedule's sessions, ordered by start_time
            sessions = schedule.sessions.all().order_by('start_time')
            
            if not sessions.exists():
                return Response({
                    "error": "No sessions found for this schedule"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get the first and last session times
            first_session = sessions.first()
            last_session = sessions.last()
            check_in_time = first_session.start_time
            check_out_time = last_session.end_time
            
            # Update attendance record
            attendance_record.check_in_time = check_in_time
            attendance_record.check_out_time = check_out_time
            attendance_record.save(update_fields=['check_in_time', 'check_out_time'])
            
            permission_request = PermissionRequest.objects.filter(student=student, schedule=schedule, status='approved').first()

            if permission_request:
                payload['adjusted_time'] = permission_request.adjusted_time

            # Ensure student is marked as checked out (since we're recording past attendance)
            if student.is_checked_in:
                student.is_checked_in = False
                student.save(update_fields=['is_checked_in'])
            
            logger.info(f"Manually recorded attendance for {student.user.email} on {schedule.name} with check-in: {check_in_time} and check-out: {check_out_time}")

            payload = {
                "status": "success",
                "message": "Attendance successfully recorded",
                "student": student.user.email,
                "schedule": schedule.name,
                "check_in_time": check_in_time,
                "check_out_time": check_out_time
            }
            
            return Response(payload, status=status.HTTP_200_OK)
        except AttendanceRecord.DoesNotExist:
            return Response({
                "error": f"Attendance record with ID {pk} not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error manually recording attendance: {str(e)}")
            return Response({
                "error": f"An error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['GET'], url_path='upcoming-records')
    def get_upcoming_records(self, request):
        """
        Get upcoming attendance records for the logged-in student.
        Returns attendance records where the schedule date is today or in the future.
        """
        try:
            # Get the logged-in user's student profile
            student = Student.objects.get(user=request.user)

            # check if student is active
            if not student.user.is_active:
                logger.warning(f"Student {student.user.email} is not active")
                return Response({
                    "status": "error",
                    "message": "Your account is not active. Please contact an administrator.",
                    "error_code": "account_not_active"
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get current date
            today = timezone.now().date()
            
            # Fetch attendance records where schedule date is today or in the future
            upcoming_records = AttendanceRecord.objects.filter(
                student=student,
                schedule__created_at__gte=today,
                check_in_time__isnull=True,  # Ensure check-in time is not set
            ).order_by('schedule__created_at')
            
            student_permission_request = PermissionRequest.objects.filter(student=student)
            if student_permission_request.exists():
                upcoming_records = upcoming_records.exclude(schedule__id__in=student_permission_request.values_list('schedule__id', flat=True))
            
            serializer = AttendanceRecordSerializerForStudents(upcoming_records, many=True)
            
            return Response({
                "status": "success",
                "data": serializer.data
            })
        except Student.DoesNotExist:
            return Response({
                "status": "error",
                "message": "No student record found for the logged-in user."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching upcoming attendance records: {str(e)}")
            return Response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)            
    @action(detail=False, methods=['GET'], url_path='weekly-breakdown')
    def get_weekly_attendance_by_track(self, request):
        """
        Get attendance percentage breakdown for each track from Saturday to Friday.
        If no track_id is provided, returns data for all tracks managed by the logged-in supervisor.
        """
        try:
            supervisor = request.user
            track_id = request.query_params.get('track_id')

            # Filter tracks
            if track_id:
                tracks = Track.objects.filter(id=track_id, supervisor=supervisor)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "Invalid track ID or you are not the supervisor of this track."
                    }, status=status.HTTP_403_FORBIDDEN)
            else:
                tracks = Track.objects.filter(supervisor=supervisor)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "You are not assigned as a supervisor to any track."
                    }, status=status.HTTP_403_FORBIDDEN)

            # Week range: Saturday to Friday
            today = timezone.now().date()
            weekday = today.weekday()
            days_since_saturday = (weekday - 5) % 7
            start_of_week = today - timedelta(days=days_since_saturday)
            week_dates = [start_of_week + timedelta(days=i) for i in range(7)]

            response_data = OrderedDict()

            for date in week_dates:
                day_name = calendar.day_name[date.weekday()]
                daily_data = {}
                total_expected_records = 0
                total_actual_records = 0

                for track in tracks:
                    schedules = Schedule.objects.filter(
                        track=track,
                        created_at=date
                    )

                    if not schedules.exists():
                        daily_data[track.name] = {
                            "status": "Free Day"
                        }
                        continue

                    total_students = Student.objects.filter(track=track).count()
                    expected_records = total_students * schedules.count()
                    actual_records = AttendanceRecord.objects.filter(
                        student__track=track,
                        schedule__in=schedules,
                        check_in_time__isnull=False
                    ).count()

                    present_percent = (actual_records / expected_records) * 100 if expected_records else 0
                    absent_percent = 100 - present_percent

                    daily_data[track.name] = {
                        "expected_attendance_records": expected_records,
                        "actual_attendance_records": actual_records,
                        "present_percent": round(present_percent, 2),
                        "absent_percent": round(absent_percent, 2)
                    }

                    # Aggregate totals for "All tracks"
                    total_expected_records += expected_records
                    total_actual_records += actual_records

                # Calculate the "All tracks" data
                if total_expected_records > 0:
                    all_tracks_present_percent = (total_actual_records / total_expected_records) * 100
                    all_tracks_absent_percent = 100 - all_tracks_present_percent
                else:
                    all_tracks_present_percent = 0
                    all_tracks_absent_percent = 0

                daily_data["All tracks"] = {
                    "expected_attendance_records": total_expected_records,
                    "actual_attendance_records": total_actual_records,
                    "present_percent": round(all_tracks_present_percent, 2),
                    "absent_percent": round(all_tracks_absent_percent, 2)
                }

                response_data[day_name] = daily_data

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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