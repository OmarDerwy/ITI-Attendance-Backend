from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import math
import logging
from attendance_management.models import AttendanceRecord, Schedule, Student
from django.shortcuts import get_object_or_404
from users.models import CustomUser
from django.utils import timezone
from core.permissions import IsSupervisorOrAboveUser  # Changed from relative to absolute import
from ..models import PermissionRequest, Track, Session, Branch
from ..serializers import AttendanceRecordSerializer, AttendanceRecordSerializerForStudents, AttendanceRecordSerializerForSupervisors
from django.db.models import Count, Q, Prefetch
from datetime import timedelta, date, datetime
from collections import OrderedDict

import calendar
from rest_framework import status
from rest_framework.views import APIView
from dateutil.relativedelta import relativedelta

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
        today = timezone.localdate()

        
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
            current_time = timezone.localtime()
            
            # Get first session start time for lateness calculation
            sessions = schedule.sessions.all().order_by('start_time')
            if not sessions.exists():
                attendance_record.status = 'no_sessions'
                attendance_record.save(update_fields=['status'])
                return Response({
                    "status": "warning",
                    "message": "Check-in recorded, but this schedule has no sessions defined.",
                    "schedule_name": schedule.name
                })
            
            first_session = sessions.first()
            
            # Check for permission requests
            permission_request = PermissionRequest.objects.filter(
                student=student,
                schedule=schedule,
                status='approved'
            ).first()
            
            # Determine status based on timing and permissions
            is_late = current_time > (first_session.start_time + timedelta(minutes=15))
            
            if permission_request:
                # Handle approved permissions
                if permission_request.request_type == 'late_check_in':
                    if permission_request.adjusted_time and current_time <= permission_request.adjusted_time:
                        # Within approved late window
                        status_to_set = 'late-excused'
                    else:
                        # Late even beyond approved time
                        status_to_set = 'late-check-in'
                elif permission_request.request_type == 'day_excuse':
                    # Should not reach here if properly excused for the day
                    status_to_set = 'excused'
                else:
                    # Other permission types (like early_leave) - regular check-in
                    status_to_set = 'late-check-in' if is_late else 'check-in'
            else:
                # No permissions
                status_to_set = 'late-check-in' if is_late else 'check-in'
            
            # Update check_in_time and status
            attendance_record.check_in_time = current_time
            attendance_record.status = status_to_set
            attendance_record.save(update_fields=['check_in_time', 'status'])
            logger.info(f"Check-in time set for student {student.user.email} with status: {status_to_set}")
            
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
        today = timezone.localdate()
        
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
            current_time = timezone.localtime()
            
            # Get sessions for timing calculations
            sessions = schedule.sessions.all().order_by('-end_time')
            if not sessions.exists():
                attendance_record.check_out_time = current_time
                attendance_record.status = 'no_sessions'
                attendance_record.save(update_fields=['check_out_time', 'status'])
                
                # Update student check-in status
                student.is_checked_in = False
                student.save(update_fields=['is_checked_in'])
                
                return Response({
                    "status": "warning",
                    "message": "Check-out recorded, but this schedule has no sessions defined.",
                    "schedule_name": schedule.name
                })
            
            last_session = sessions.first()  # Get the session that ends last
            
            # Check for permission requests
            permission_requests = PermissionRequest.objects.filter(
                student=student,
                schedule=schedule,
                status='approved'
            )
            
            # Check if there's an early leave permission
            early_leave_permission = permission_requests.filter(request_type='early_leave').first()
            
            # Check if there was a late check-in permission
            late_checkin_permission = permission_requests.filter(request_type='late_check_in').first()
            
            # Determine if check-out is early (before session end)
            is_early_checkout = current_time < last_session.end_time
            
            # Determine base status from check-in status
            current_status = attendance_record.status
            
            # Determine final status based on check-in status, timing, and permissions
            if current_status in ['check-in']:
                # Normal check-in
                if is_early_checkout:
                    if early_leave_permission:
                        status_to_set = 'check-in_early-excused'
                    else:
                        status_to_set = 'check-in_early-check-out'
                else:
                    status_to_set = 'attended'
                    
            elif current_status in ['late-check-in']:
                # Late check-in without excuse
                if is_early_checkout:
                    if early_leave_permission:
                        status_to_set = 'late-check-in_early-excused'
                    else:
                        status_to_set = 'late-check-in_early-check-out'
                else:
                    status_to_set = 'late-check-in'
                    
            elif current_status in ['late-excused']:
                # Late check-in with excuse
                if is_early_checkout:
                    if early_leave_permission:
                        status_to_set = 'late-excused_early-excused'
                    else:
                        status_to_set = 'late-excused_early-check-out'
                else:
                    status_to_set = 'late-excused'
                    
            else:
                # Any other status (shouldn't normally happen)
                if is_early_checkout and not early_leave_permission:
                    status_to_set = 'check-in_early-check-out'
                else:
                    status_to_set = 'attended'
            
            # Update check_out_time and status
            attendance_record.check_out_time = current_time
            attendance_record.status = status_to_set
            attendance_record.save(update_fields=['check_out_time', 'status'])
            logger.info(f"Check-out time set for student {student.user.email} with status: {status_to_set}")
            
            # Set student as checked out
            student.is_checked_in = False
            student.save(update_fields=['is_checked_in'])
            logger.info(f"Student {student.user.email} marked as checked out")
            
            # Calculate duration of attendance 
            time_difference = attendance_record.check_out_time - attendance_record.check_in_time
            hours = time_difference.total_seconds() / 3600
            
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
                date = timezone.localdate()

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
         Get today's attendance percentage.
        - Admins: See percentage for all tracks
        - Branch Managers: See percentage for tracks in their branch
        - Supervisors: See percentage for their managed tracks
        - Coordinators: See percentage for all tracks in their branch
        """
        try:
            user = request.user
            user_groups = user.groups.values_list('name', flat=True)
            track_id = request.query_params.get('track_id')
            if 'admin' in user_groups:
           
                tracks = Track.objects.all()
                if not tracks.exists():
                    return Response({"status": "info", "message": "No tracks found in the system."}, 
                                status=status.HTTP_200_OK)
                
            elif 'branch-manager' in user_groups:
                branch = Branch.objects.filter(branch_manager=user).first()
                if not branch:
                    return Response({
                        "status": "error",
                        "message": "No branch found for this branch manager."
                    }, status=status.HTTP_404_NOT_FOUND)
                    
                tracks = Track.objects.filter(default_branch=branch, is_active=True)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "No tracks found in your branch."
                    }, status=status.HTTP_404_NOT_FOUND)

            elif 'supervisor' in user_groups:
                    tracks = Track.objects.filter(supervisor=user, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "You are not assigned as a supervisor to any track."
                        }, status=status.HTTP_403_FORBIDDEN)
            elif 'coordinator' in user_groups:
                coordinator_profile = user.coordinator
                tracks = Track.objects.filter(default_branch__coordinators=coordinator_profile, is_active=True)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "No tracks found in your branch."
                    }, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({
                    "status": "error",
                    "message": "You must be an admin, branch manager, supervisor, or coordinator to access this endpoint."
                }, status=status.HTTP_403_FORBIDDEN)
                    
            date = timezone.localdate()

            total_students = 0
            attended_students = 0

            for track in tracks:
                schedules = Schedule.objects.filter(track=track, created_at=date)
                scheduled_students = Student.objects.filter(
                attendance_records__schedule__in=schedules
            ).distinct().count()
                total_students += scheduled_students

                # Count how many of the scheduled students actually attended today
                attended_students += AttendanceRecord.objects.filter(
                    student__track=track,
                    schedule__in=schedules,
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
            logger.error(f"Error fetching today's attendance percentage: {str(e)}")
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['GET'], url_path='attendance-percentage/weekly')
    def get_weekly_attendance_percentage(self, request):
        """
        Get weekly attendance percentage for tracks.
        - Admins: See percentage for all tracks
        - Branch Managers: See percentage for tracks in their branch
        - Supervisors: See percentage for their managed tracks
        - Coordinators: See percentage for all tracks in their branch
        """
        try:
            user = request.user
            user_groups = user.groups.values_list('name', flat=True)
            if 'admin' in user_groups:
                tracks = Track.objects.filter(is_active=True)
                if not tracks.exists():
                    return Response({
                        "status": "info", 
                        "message": "No tracks found in the system."
                    }, status=status.HTTP_200_OK)

            elif 'branch-manager' in user_groups:
                branch = Branch.objects.filter(branch_manager=user).first()
                if not branch:
                    return Response({
                        "status": "error",
                        "message": "No branch found for this branch manager."
                    }, status=status.HTTP_404_NOT_FOUND)
                tracks = Track.objects.filter(default_branch=branch, is_active=True)

            elif 'supervisor' in user_groups:
                tracks = Track.objects.filter(supervisor=user, is_active=True)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "You are not assigned as a supervisor to any track."
                    }, status=status.HTTP_403_FORBIDDEN)
            elif 'coordinator' in user_groups:
                coordinator_profile = user.coordinator
                tracks = Track.objects.filter(default_branch__coordinators=coordinator_profile, is_active=True)
                if not tracks.exists():
                    return Response({
                        "status": "error",
                        "message": "No tracks found in your branch."
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({
                    "status": "error",
                    "message": "You must be an admin, branch manager, supervisor, or coordinator to access this endpoint."
                }, status=status.HTTP_403_FORBIDDEN)

            end_date = timezone.localdate()
            start_date = end_date - timedelta(days=7)
            total_students = Student.objects.filter(track__in=tracks).count()
            # Get schedules in the past week
            schedules = Schedule.objects.filter(
                track__in=tracks,
                created_at__range=(start_date, end_date)
            )
            num_schedules = schedules.count()

            # Calculate expected attendance count by aggregating per track
            expected_attendance_count = sum(
                Student.objects.filter(track=track).count() * Schedule.objects.filter(track=track, created_at__range=(start_date, end_date)).count()
                for track in tracks
            )

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

    @action(detail=False, methods=['GET'], url_path='attendance-trends', permission_classes=[IsSupervisorOrAboveUser])
    def get_attendance_trends(self, request):
        """
        Get attendance trends over time.
        - Admins: See trends for all tracks
        - Branch Managers: See trends for tracks in their branch
        - Supervisors: See trends for their managed tracks
        - Coordinators: See trends for all tracks in their branch
        """
        try:
            user = request.user
            user_groups = list(user.groups.values_list('name', flat=True))
            track_id = request.query_params.get('track_id')
            branch_id = request.query_params.get('branch_id')
            track_id = request.query_params.get('track_id')
            branch_id = request.query_params.get('branch_id') 
            if 'admin' in user_groups:
                tracks_query = Track.objects.filter(is_active=True)
                if branch_id:
                    tracks_query = tracks_query.filter(default_branch_id=branch_id)
                if not tracks_query.exists():
                    return Response({
                        "status": "info",
                        "message": "No tracks found in the system."
                    }, status=status.HTTP_200_OK)

            elif 'branch-manager' in user_groups:
                branch = Branch.objects.filter(branch_manager=user).first()
                if not branch:
                    return Response({
                        "status": "error",
                        "message": "No branch found for this branch manager."
                    }, status=status.HTTP_404_NOT_FOUND)
                
                tracks_query = Track.objects.filter(default_branch=branch, is_active=True)
                if not tracks_query.exists():
                    return Response({
                        "status": "error",
                        "message": "No tracks found in your branch."
                    }, status=status.HTTP_404_NOT_FOUND)

            elif 'supervisor' in user_groups:
                tracks_query = Track.objects.filter(supervisor=user, is_active=True)
                if not tracks_query.exists():
                    return Response({
                        "status": "error",
                        "message": "You are not assigned as a supervisor to any track."
                    }, status=status.HTTP_403_FORBIDDEN)

            elif 'coordinator' in user_groups:
                coordinator_profile = user.coordinator
                tracks_query = Track.objects.filter(default_branch__coordinators=coordinator_profile, is_active=True)
                if not tracks_query.exists():
                    return Response({
                        "status": "error",
                        "message": "No tracks found in your branch."
                    }, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({
                    "status": "error",
                    "message": "You must be an admin, branch manager, supervisor, or coordinator to access this endpoint."
                }, status=status.HTTP_403_FORBIDDEN)

            if track_id:
                tracks_query = tracks_query.filter(id=track_id)
                if not tracks_query.exists():
                    return Response({
                        "status": "error",
                        "message": "The specified track does not exist or is not managed by you."
                    }, status=status.HTTP_404_NOT_FOUND)

            # Calculate date ranges
            today = timezone.now().date()
            thirty_days_ago = today - timedelta(days=30)
            four_weeks_ago = today - timedelta(weeks=4)

            # Get track students count
            track_students = {
                track.id: Student.objects.filter(track=track).count()
                for track in tracks_query
            }

            # Get attendance data in a single query
            schedule_data = (
                Schedule.objects.filter(
                    track__in=tracks_query,
                    created_at__gte=four_weeks_ago,
                    created_at__lte=today
                )
                .values('track__id', 'track__name', 'created_at')
                .annotate(
                    attended=Count('attendance_records', filter=Q(attendance_records__check_in_time__isnull=False)),
                    total_students=Count('track__students')
                )
                .order_by('created_at')
            )

            # Process daily trends and weekly aggregation
            daily_trends = []
            weekly_data = {}

            for record in schedule_data:
                date = record['created_at']
                track_name = record['track__name']
                attended = record['attended']
                expected = record['total_students']

                # Daily trends - only include data from the last 30 days
                if date >= thirty_days_ago and date <= today:
                    daily_trends.append({
                        "date": date,
                        "track": track_name,
                        "attended": attended,
                        "expected": expected
                    })

                # Weekly trends - aggregate all tracks per week
                if date >= four_weeks_ago and date <= today:
                    week_num = date.isocalendar()[1]
                    if track_id:
                        # If filtering by track, keep track name in the key
                        week_key = (week_num, track_name)
                    else:
                        # If showing all tracks, aggregate by week only
                        week_key = week_num
                        
                    if week_key not in weekly_data:
                        weekly_data[week_key] = {'attended': 0, 'expected': 0}
                    weekly_data[week_key]['attended'] += attended
                    weekly_data[week_key]['expected'] += expected

            # Convert weekly data to list format
            weekly_trends = []
            for week_key, data in sorted(weekly_data.items()):
                if isinstance(week_key, tuple):
                    # Data for specific track
                    week_num, track_name = week_key
                    weekly_trends.append({
                        "week": week_num,
                        "track": track_name,
                        "attended": data['attended'],
                        "expected": data['expected']
                    })
                else:
                    # Aggregated data for all tracks
                    weekly_trends.append({
                        "week": week_key,
                        "track": "All Tracks",
                        "attended": data['attended'],
                        "expected": data['expected']
                    })

            response_data = {
                "daily_trends": sorted(daily_trends, key=lambda x: x['date']),
                "weekly_trends": weekly_trends
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching attendance trends: {str(e)}")
            return Response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
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
            attendance_record.status = 'absent'
            attendance_record.save(update_fields=['check_in_time', 'check_out_time', 'status'])

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
            attendance_record.status = 'attended'  # Manually set records get 'attended' status
            attendance_record.save(update_fields=['check_in_time', 'check_out_time', 'status'])
            
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

    @action(detail=False, methods=['GET'], url_path='todays-schedule')
    def get_todays_schedule(self, request):
        '''
        STUDENT ONLY
        Get today's schedule for the logged-in student. if no schedule exists today then return none
        '''
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

            today = timezone.localdate()
            schedule = AttendanceRecord.objects.filter(
                student=student,
                schedule__created_at=today,
            ).prefetch_related('schedule__sessions').first()

            if not schedule:
                return Response({
                    "status": "info",
                    "message": "No schedule found for today.",
                    "data": None
                }, status=status.HTTP_200_OK)

            serializer = AttendanceRecordSerializerForStudents(schedule)
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
            logger.error(f"Error fetching today's schedule: {str(e)}")
            return Response({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
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

            ##### PAST FUNCTIONALITY #####
            # # Fetch attendance records where schedule date is today or in the future
            # upcoming_records = AttendanceRecord.objects.filter(
            #     student=student,
            #     schedule__created_at__gte=today,
            #     check_in_time__isnull=True,  # Ensure check-in time is not set
            # ).order_by('schedule__created_at')
            ###############################
            upcoming_records = AttendanceRecord.objects.filter(
                student=student,
            ).exclude(
                schedule__sessions__end_time__lt=timezone.localtime()
            ).distinct().order_by('schedule__created_at')
            
            student_permission_request = PermissionRequest.objects.filter(student=student, status='approved', request_type='day_excuse')
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
    @action(detail=False, methods=['GET'], url_path='upcoming-records-gt')
    def get_upcoming_records_gt(self, request):
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

            ##### PAST FUNCTIONALITY #####
            # # Fetch attendance records where schedule date is today or in the future
            # upcoming_records = AttendanceRecord.objects.filter(
            #     student=student,
            #     schedule__created_at__gte=today,
            #     check_in_time__isnull=True,  # Ensure check-in time is not set
            # ).order_by('schedule__created_at')
            ###############################
            upcoming_records = AttendanceRecord.objects.filter(
                student=student,
                schedule__sessions__end_time__gt=timezone.localtime()
            ).distinct().order_by('schedule__created_at')
            
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
        For supervisors: Shows data for their managed tracks
        For coordinators: Shows data for all tracks in their branch
        """
        try:
            user = request.user
            user_groups = user.groups.values_list('name', flat=True)
            track_id = request.query_params.get('track_id')

            # Initialize tracks queryset based on user role
            if 'supervisor' in user_groups:
                if track_id:
                    tracks = Track.objects.filter(id=track_id, supervisor=user, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "Invalid track ID or you are not the supervisor of this track."
                        }, status=status.HTTP_403_FORBIDDEN)
                else:
                    tracks = Track.objects.filter(supervisor=user, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "You are not assigned as a supervisor to any track."
                        }, status=status.HTTP_403_FORBIDDEN)
            elif 'coordinator' in user_groups:
                coordinator_profile = user.coordinator
                if track_id:
                    tracks = Track.objects.filter(id=track_id, default_branch__coordinators=coordinator_profile, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "Invalid track ID or this track is not in your branch."
                        }, status=status.HTTP_403_FORBIDDEN)
                else:
                    tracks = Track.objects.filter(default_branch__coordinators=coordinator_profile, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "No tracks found in your branch."
                        }, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({
                    "status": "error",
                    "message": "You must be either a supervisor or coordinator to access this endpoint."
                }, status=status.HTTP_403_FORBIDDEN)

            today = timezone.localdate()
            weekday = today.weekday()
            days_since_saturday = (weekday - 5) % 7
            start_of_week = today - timedelta(days=days_since_saturday)
            week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
            # Exclude upcoming days beyond today
            week_dates = [d for d in week_dates if d <= today]
            # Exclude today if the first session hasn't started yet
            if today in week_dates:
                first_session = Session.objects.filter(
                    schedule__track__in=tracks,
                    schedule__created_at=today
                ).order_by('start_time').first()
                if first_session and first_session.start_time > timezone.localtime():
                    week_dates.remove(today)
            response_data = OrderedDict()

            for date in week_dates:
                day_name = calendar.day_name[date.weekday()]
                daily_data = {}
                total_expected_records = 0
                total_actual_records = 0

                for track in tracks:
                    schedules = Schedule.objects.filter(track=track, created_at=date)

                    if not schedules.exists():
                        daily_data[track.name] = {
                            "status": "Free Day"
                        }
                        continue

                    # Count only students scheduled today
                    scheduled_students = Student.objects.filter(
                        attendance_records__schedule__in=schedules
                    ).distinct().count()
                    
                    total_students = scheduled_students
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


    @action(detail=False, methods=['get'], url_path='recent-absences')
    def recent_absences(self, request, *args, **kwargs):
        """
        Get recent absences with optional track filtering.
        Query Parameters:
            track_id (optional): Filter results for a specific track
        """
        try:
            user = request.user
            user_groups = user.groups.values_list('name', flat=True)
            today = date.today()
            track_id = request.query_params.get('track_id')
            if track_id:
                tracks = tracks.filter(id=track_id, is_active=True)
                
            if 'supervisor' in user_groups:
                if track_id:
                    tracks = Track.objects.filter(id=track_id, supervisor=user, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "Invalid track ID or you are not the supervisor of this track."
                        }, status=status.HTTP_403_FORBIDDEN)
                else:
                    tracks = Track.objects.filter(supervisor=user, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "You are not assigned as a supervisor to any track."
                        }, status=status.HTTP_403_FORBIDDEN)
            elif 'coordinator' in user_groups:
                coordinator_profile = user.coordinator
                if track_id:
                    tracks = Track.objects.filter(id=track_id, default_branch__coordinators=coordinator_profile, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "Invalid track ID or this track is not in your branch."
                        }, status=status.HTTP_403_FORBIDDEN)
                else:
                    tracks = Track.objects.filter(default_branch__coordinators=coordinator_profile, is_active=True)
                    if not tracks.exists():
                        return Response({
                            "status": "error",
                            "message": "No tracks found in your branch."
                        }, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({
                    "status": "error",
                    "message": "You must be either a supervisor or coordinator to access this endpoint."
                }, status=status.HTTP_403_FORBIDDEN)

            # Get all absences with a single optimized query
            absence_records = (
                AttendanceRecord.objects
                .filter(
                    schedule__created_at=today,
                    student__track__in=tracks,
                    status__in=['absent', 'excused']
                )
                .select_related('student__user', 'schedule')
                .prefetch_related(
                    Prefetch(
                        'schedule__permission_requests',
                        queryset=PermissionRequest.objects.filter(
                            status='approved'
                        ),
                        to_attr='active_permissions'
                    )
                )
            )

            # Process records in batches
            formatted_data = []
            batch_size = 100
            
            for i in range(0, len(absence_records), batch_size):
                batch = absence_records[i:i + batch_size]
                for record in batch:
                    formatted_data.append({
                        "student": f"{record.student.user.first_name or ''} {record.student.user.last_name or ''}".strip(),
                        "date": record.schedule.created_at.strftime("%b %d, %Y"),
                        "reason": record.schedule.active_permissions[0].reason if record.schedule.active_permissions else "no reason found",
                        "status": record.status,
                    })

            return Response(formatted_data)
        except Exception as e:
            logger.error(f"Error fetching recent absences: {str(e)}")
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
    @action(detail=False, methods=["get"], url_path="calendar")
    def calendar(self, request):
        supervisor= request.user
        track_id = request.query_params.get('track_id')
        page = int(request.query_params.get('page', 0))
        now = datetime.now()
        
        # Each page = 2 months shift (0 = this + next, -1 = prev two, etc.)
        # Always start at the first of the current month
        now = datetime.now()
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # For page=0: current & previous month (e.g., April & March)
        # For page=1: previous two months, etc.
        start_date = current_month_start - relativedelta(months=page * 2 + 1)
        end_date = start_date + relativedelta(months=2)
        if end_date > now + relativedelta(days=1):
            end_date = now + relativedelta(days=1)
        tracks = Track.objects.filter(supervisor=supervisor)
        if track_id:
            tracks = tracks.filter(id=track_id)

        schedules = Schedule.objects.filter(
            track__in=tracks,
            created_at__gte=start_date,
            created_at__lt=end_date
        ).select_related('track')

        attendance_counts = AttendanceRecord.objects.filter(
            schedule__in=schedules,
            check_in_time__isnull=False
        ).values('schedule').annotate(count=Count('id'))
        attendance_map = {item['schedule']: item['count'] for item in attendance_counts}

        result = {}

        for schedule in schedules:
            date_str = schedule.created_at.strftime('%Y-%m-%d')
            total_students = schedule.track.students.count()
            attended_count = attendance_map.get(schedule.id, 0)
            percentage = (attended_count / total_students * 100) if total_students > 0 else 0.0
            result[date_str] = round(percentage, 1)

        return Response({
            "start_month": start_date.strftime("%B"),
            "end_month": (end_date - relativedelta(days=1)).strftime("%B"),
            "year": start_date.year,
            "calendar": result
        }, status=status.HTTP_200_OK)


    @action(detail=False, methods=['GET'], url_path='student-attendance')
    def get_student_attendance(self, request):
        """
        Get attendance records of the logged-in student for all past days including today.
        Returns records in descending order (newest first).
        """
        try:
            # Get the logged-in user's student profile
            student = Student.objects.get(user=request.user)

            # Check if student is active
            # if not student.user.is_active:
            #     logger.warning(f"Student {student.user.email} is not active")
            #     return Response({
            #         "status": "error",
            #         "message": "Your account is not active. Please contact an administrator."
            #     }, status=status.HTTP_403_FORBIDDEN)
            
            # Get today's date
            today = timezone.localdate()
            
            # Get today's and all past records
            attendance_records = AttendanceRecord.objects.filter(
                student=student,
                schedule__created_at__lte=today
            ).order_by('-schedule__created_at')  # Most recent first
                
            serializer = AttendanceRecordSerializerForStudents(attendance_records, many=True)
            
            # Return simpler response structure
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Student.DoesNotExist:
            return Response({
                "error": "No student record found for the logged-in user."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching student attendance records: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    @action(detail=True, methods=['GET'], url_path='student-history', permission_classes=[IsSupervisorOrAboveUser])
    def get_student_attendance_history(self, request, pk=None):
        """
        Get attendance records of a specific student by ID.
        Only accessible by supervisors who manage the student's track.
        
        URL: /api/v1/attendance/{student_id}/student-history/
        """
        try:
            # Get the supervisor (logged-in user)
            request_user = request.user
            
            # Get the student by ID (from URL parameter)
            student = get_object_or_404(Student, user_id=pk)
            
            # Check if student belongs to a track supervised by this supervisor
            if student.track.supervisor != request_user and not student.track.default_branch.coordinators.filter(user=request_user).exists():
                logger.warning(f"User {request_user.email} attempted to access attendance data for student {student.user.email} in unauthorized track")
                return Response({
                    "status": "error",
                    "message": "You are not authorized to view attendance records for this student."
                }, status=status.HTTP_403_FORBIDDEN)

            # Get optional date range from query parameters
            start_date_str = request.query_params.get('start_date')
            end_date_str = request.query_params.get('end_date')
            
            # Default to all past records if no dates provided
            query_filters = {
                'student': student,
                'schedule__created_at__lte': timezone.localdate()
            }
            
            # Apply date filters if provided - UNTESTED!
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                    query_filters['schedule__created_at__gte'] = start_date
                except ValueError:
                    return Response({
                        "status": "error", 
                        "message": "Invalid start_date format. Use YYYY-MM-DD."
                    }, status=status.HTTP_400_BAD_REQUEST)
                    
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                    query_filters['schedule__created_at__lte'] = end_date
                except ValueError:
                    return Response({
                        "status": "error",
                        "message": "Invalid end_date format. Use YYYY-MM-DD."
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get attendance records with optimized queries
            attendance_records = AttendanceRecord.objects.filter(**query_filters).order_by('-schedule__created_at')  # Most recent first
            
            # Get attendance aggregate for this student
            user_attendance_records = AttendanceRecord.objects.filter(
                student=student,
                schedule__sessions__end_time__lt=timezone.localtime()
            ).distinct()  # TODO this code is weird, make sure it works
            num_of_attendance_records = user_attendance_records.count()
            num_of_times_attended = user_attendance_records.exclude(check_in_time__isnull=True).count()
            num_of_times_absent = num_of_attendance_records - num_of_times_attended
            aggregate_payload = {
                'num_of_attendance_records': num_of_attendance_records,
                'num_of_times_attended': num_of_times_attended,
                'num_of_times_absent': num_of_times_absent,
                'attendance_percentage': (num_of_times_attended / num_of_attendance_records) * 100 if num_of_attendance_records > 0 else 0,
            }


            serializer = AttendanceRecordSerializerForSupervisors(attendance_records, many=True)
            
            # Include student information in the response
            response_data = {
                "student_info": { # extra data yasta law 7d 3ayez ya3ny
                    "id": student.id,
                    "name": f"{student.user.first_name} {student.user.last_name}",
                    "email": student.user.email,
                    "track": student.track.name,
                    "is_active": student.user.is_active
                },
                "attendance_aggregate": aggregate_payload,
                "attendance_records": serializer.data,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Student.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Student not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching student attendance history: {str(e)}")
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['GET'], url_path='student-attendance-summary')
    def get_student_attendance_summary(self, request):
        """
        Get a lightweight summary of attendance records for the logged-in student.
        Only returns date and status for better performance.
        """
        try:
            # Get the logged-in user's student profile
            student = Student.objects.get(user=request.user)
            
            # Get today's date
            today = timezone.localdate()
            
            # Efficient JOIN between AttendanceRecord and Schedule tables
            records = AttendanceRecord.objects.filter(
                student=student,
                schedule__created_at__lte=today
            ).select_related('schedule').only(
                'status', 'schedule__created_at'
            ).values('status', 'schedule__created_at')
            
            # Build a simple response with just the needed fields
            result = [
                {
                    'date': record['schedule__created_at'],
                    'status': record['status'],
                }
                for record in records
            ]
            
            return Response(result, status=200)

        except Student.DoesNotExist:
            return Response({
                "error": "No student record found for the logged-in user."
            }, status=404)
        except Exception as e:
            logger.error(f"Error fetching student attendance summary: {str(e)}")
            return Response({
                "error": str(e)
            }, status=500)

    @action(detail=False, methods=['GET'], url_path='attendance-stats')
    def get_attendance_stats(self, request):
        """
        Get attendance statistics for the logged-in student.
        Returns:
        - Total attended days
        - Total absent days
        - Attendance percentage
        - Status based on thresholds (good, warning, danger)
        """
        try:
            # Get the logged-in user's student profile
            student = Student.objects.get(user=request.user)
            
            # Get student's program type from track
            program_type = student.track.program_type
            
            # Get threshold values based on program type from application settings
            from ..models import ApplicationSetting
            unexcused_threshold = ApplicationSetting.get_unexcused_absence_threshold(program_type)
            excused_threshold = ApplicationSetting.get_excused_absence_threshold(program_type)
            
            # Fetch past attendance records
            today = timezone.localdate()
            past_records = AttendanceRecord.objects.filter(
                student=student,
                schedule__created_at__lte=today,
                schedule__sessions__isnull=False,  # Ensure there were sessions
            ).distinct()
            
            # Count attendance data
            total_days = past_records.count()
            total_attended = past_records.filter(Q(check_in_time__isnull=False) | Q(status='attended')).count()
            
            
            # Get excused and unexcused absences
            unexcused_absences = student.get_unexcused_absence_count()
            excused_absences = student.get_excused_absence_count()
            total_absent = unexcused_absences + excused_absences
            # Calculate percentage
            attendance_percentage = (total_attended / total_days) * 100 if total_days > 0 else 0
            
            # Determine status
            attendance_status = "good"
            if unexcused_absences >= unexcused_threshold or excused_absences >= excused_threshold:
                attendance_status = "danger"
            elif unexcused_absences >= unexcused_threshold * 0.7 or excused_absences >= excused_threshold * 0.7:
                attendance_status = "warning"
            
            return Response({
                "total_days": total_days,
                "total_attended": total_attended,
                "total_absent": total_absent,
                "unexcused_absences": unexcused_absences,
                "excused_absences": excused_absences,
                "attendance_percentage": round(attendance_percentage, 2),
                "attendance_status": attendance_status,
                "program_type": program_type,
                "thresholds": {
                    "unexcused_threshold": unexcused_threshold,
                    "excused_threshold": excused_threshold,
                    "unexcused_consumed": f"{unexcused_absences}/{unexcused_threshold}",
                    "excused_consumed": f"{excused_absences}/{excused_threshold}"
                }
            }, status=status.HTTP_200_OK)
            
        except Student.DoesNotExist:
            return Response({
                "error": "No student record found for the logged-in user."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching attendance stats: {str(e)}")
            return Response({
                "error": str(e)
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