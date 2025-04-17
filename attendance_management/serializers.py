from rest_framework import serializers
from .models import Schedule, Session, Student, Track, Branch, AttendanceRecord, PermissionRequest
from users.models import CustomUser
from datetime import datetime, timedelta
from .settings_models import ApplicationSetting

class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['id', 'title', 'instructor', 'start_time', 'end_time', 'session_type', 'schedule']

class MiniTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = ['id', 'name']

class ScheduleSerializer(serializers.ModelSerializer):
    track = MiniTrackSerializer(read_only=True)  # Read-only field for track
    sessions = serializers.StringRelatedField(many=True, read_only=True)  # Read-only field for sessions
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    attended_out_of_total = serializers.SerializerMethodField()
    
    class Meta:
        model = Schedule
        fields = ['id','name', 'track', 'created_at', 'sessions', 'custom_branch', 'is_shared', 'start_time', 'end_time', 'attended_out_of_total']

    def get_start_time(self, obj):
        """Get the start time from the first session of the day"""
        first_session = Session.objects.filter(schedule=obj).order_by('start_time').first()
        return first_session.start_time if first_session else None
        
    def get_end_time(self, obj):
        """Get the end time from the last session of the day"""
        last_session = Session.objects.filter(schedule=obj).order_by('-end_time').first()
        return last_session.end_time if last_session else None

    def get_fields(self):
        fields = super().get_fields()
        view = self.context.get('view')
        if view and view.action == 'retrieve':
            fields['attendance_records'] = AttendanceRecordSerializer(many=True, read_only=True)
        return fields
    
    def get_attended_out_of_total(self, obj):
        """
        Calculate the number of students attended the schedule out of total students in the track using the available attendance records.
        """
        total_students = obj.attendance_records.count()
        attended_students = AttendanceRecord.objects.filter(schedule=obj, check_in_time__isnull=False).values_list('student', flat=True).distinct().count()
        
        return {
            "attended": attended_students,
            "total": total_students
        }
        
class StudentSerializer(serializers.ModelSerializer):  # Updated to use Student
    class Meta:
        model = Student
        fields = ['id', 'user', 'track']

class TrackSerializer(serializers.ModelSerializer):
    branch_id = serializers.IntegerField(write_only=True)  # For POST/PUT requests
    supervisor_id = serializers.IntegerField(write_only=True)  # For POST/PUT requests
    track_id = serializers.IntegerField(source='id', read_only=True)
    default_branch = serializers.StringRelatedField(read_only=True)  # Readable branch name
    supervisor = serializers.SerializerMethodField(read_only=True)  # Get supervisor full name
    program_type = serializers.ChoiceField(choices=Track.PROGRAM_CHOICES)
    program_type_display = serializers.CharField(source='get_program_type_display', read_only=True)

    def get_supervisor(self, obj):
        if obj.supervisor:
            return f"{obj.supervisor.first_name} {obj.supervisor.last_name}"
        return None

    def to_representation(self, instance):
        """Customize the GET response to include branch_id and supervisor_id."""
        representation = super().to_representation(instance)
        representation['branch_id'] = instance.default_branch.id if instance.default_branch else None
        representation['supervisor_id'] = instance.supervisor.id if instance.supervisor else None
        return representation

    def update(self, instance, validated_data):
        # Get foreign key IDs from request
        branch_id = validated_data.pop('branch_id', None)
        supervisor_id = validated_data.pop('supervisor_id', None)

        # Assign new branch and supervisor if provided
        if branch_id:
            try:
                instance.default_branch = Branch.objects.get(id=branch_id)
            except Branch.DoesNotExist:
                raise serializers.ValidationError({"branch_id": f"Branch with ID {branch_id} does not exist."})

        if supervisor_id:
            try:
                instance.supervisor = CustomUser.objects.get(id=supervisor_id)
            except CustomUser.DoesNotExist:
                raise serializers.ValidationError({"supervisor_id": f"User with ID {supervisor_id} does not exist."})

        # Update remaining fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def create(self, validated_data):
        # Extract foreign key IDs
        branch_id = validated_data.pop('branch_id', None)
        supervisor_id = validated_data.pop('supervisor_id', None)

        # Ensure branch_id and supervisor_id are provided
        if not branch_id:
            raise serializers.ValidationError({"branch_id": "This field is required."})
        if not supervisor_id:
            raise serializers.ValidationError({"supervisor_id": "This field is required."})

        # Fetch the default_branch instance
        try:
            default_branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            raise serializers.ValidationError({"branch_id": f"Branch with ID {branch_id} does not exist."})

        # Fetch the supervisor instance
        try:
            supervisor = CustomUser.objects.get(id=supervisor_id)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"supervisor_id": f"User with ID {supervisor_id} does not exist."})

        # Assign default_branch and supervisor to validated_data
        validated_data['default_branch'] = default_branch
        validated_data['supervisor'] = supervisor

        # Create track object
        track = Track.objects.create(**validated_data)
        return track

    class Meta:
        model = Track
        fields = '__all__'

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'latitude', 'longitude', 'location_url', 'radius']

class AttendanceRecordSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()  # updated student field
    status = serializers.SerializerMethodField()
    adjusted_time = serializers.SerializerMethodField()
    leave_request_status = serializers.SerializerMethodField()
    track_name = serializers.SerializerMethodField()  
    warning_status = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'student',
            'schedule',
            'check_in_time',
            'check_out_time',
            'leave_request_status', # for checking if this attendance record is pending leave request or not
            'status', 
            'adjusted_time',
            'leave_request_status',
            'track_name',
            'warning_status'
        ]

    def get_student(self, obj):
        return {
            'id': obj.student.id,
            'name': f"{obj.student.user.first_name} {obj.student.user.last_name}",
            'email': obj.student.user.email
        }

    def get_status(self, obj):
        """
        Determine the status of the attendance record based on the conditions.
        # Possible statuses:
        # - 'excused': Student has an approved day excuse.
        # - 'pending': Schedule is in the future OR student has a pending permission request and hasn't checked in.
        # - 'no_sessions': Schedule has no sessions defined.
        # - 'excused_late': Student has approved late permission, is within the adjusted time, but hasn't checked in yet.
        # - 'absent': Student did not check in and is past the deadline or excused late window.
        # - 'check-in': Student checked in on time, session is ongoing.
        # - 'late-check-in_active': Student checked in late (no excuse), session is ongoing.
        # - 'late-excused_active': Student checked in late (with excuse), session is ongoing.
        # - 'no-check-out': Student checked in on time, but did not check out after the session ended.
        # - 'late-check-in_no-check-out': Student checked in late (no excuse), did not check out after the session ended.
        # - 'late-excused_no-check-out': Student checked in late (with excuse), did not check out after the session ended.
        # - 'attended': Student checked in on time and checked out on time or later.
        # - 'late-check-in': Student checked in late (no excuse) and checked out on time or later.
        # - 'late-excused': Student checked in late (with excuse) and checked out on time or later.
        # - 'check-in_early-check-out': Student checked in on time but checked out early (no excuse).
        # - 'late-check-in_early-check-out': Student checked in late (no excuse) and checked out early (no excuse).
        # - 'late-excused_early-check-out': Student checked in late (with excuse) and checked out early (no excuse).
        # - 'check-in_early-excused': Student checked in on time and checked out early (with excuse).
        # - 'late-check-in_early-excused': Student checked in late (no excuse) and checked out early (with excuse).
        # - 'late-excused_early-excused': Student checked in late (with excuse) and checked out early (with excuse).
        """
        student = obj.student
        schedule = obj.schedule
        today = datetime.now().date()
        now = datetime.now()

        def has_permission(request_type):
            return PermissionRequest.objects.filter(
                student=student,
                schedule=schedule,
                request_type=request_type,
                status='approved'
            ).first()

        if not obj.check_in_time and not obj.check_out_time:
            if permission_request and permission_request.status == 'approved':
                return 'excused'
            return 'absent'
        elif obj.check_in_time and not obj.check_out_time:
            return 'no-check-out'
        elif obj.check_in_time and obj.check_out_time:
            return 'present'
        return 'unknown'

    def get_adjusted_time(self, obj):
        # Get permission request for this attendance record
        permission_request = PermissionRequest.objects.filter(
            student=obj.student,
            schedule=obj.schedule,
            status='approved'
        ).first()
        return permission_request.adjusted_time if permission_request else None

    def get_leave_request_status(self, obj):
        # Get permission request for this attendance record
        permission_request = PermissionRequest.objects.filter(
            student=obj.student,
            schedule=obj.schedule
        ).first()
        return permission_request.status if permission_request else 'none'

    def get_track_name(self, obj):
        return obj.student.track.name

    def get_warning_status(self, obj):
        has_warning, warning_type = obj.student.has_exceeded_warning_threshold()
        return warning_type if has_warning else None

class AttendanceRecordSerializerForStudents(AttendanceRecordSerializer):
    schedule = ScheduleSerializer(read_only=True)  # Read-only field for schedule
    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 
            'schedule', 
            'check_in_time', 
            'check_out_time',
            'status',
            'adjusted_time'
        ]
class AttendanceRecordSerializerForSupervisors(AttendanceRecordSerializer):
    sessions = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    class Meta:
        model = AttendanceRecord
        fields = [
            'id',
            'schedule',
            'sessions',
            'check_in_time', 
            'check_out_time',
            'status',
            'adjusted_time'
        ]
    def get_sessions(self, obj):
        """
        Return the sessions related to the schedule of the attendance record.
        """
        sessions = Session.objects.filter(schedule=obj.schedule).values_list('title', flat=True)
        return sessions
    def get_schedule(self, obj):
        """
        Return the schedule name related to the attendance record.
        """
        return {
            'id': obj.schedule.id,
            'name': obj.schedule.name,
            'created_at': obj.schedule.created_at,
            'track': {
                'id': obj.schedule.track.id,
                'name': obj.schedule.track.name
            }
        }

class PermissionRequestSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()  # updated student field
    schedule = ScheduleSerializer(read_only=False)  # Read-only field for schedule
    class Meta:
        model = PermissionRequest
        fields = [
            'id', 
            'student', 
            'schedule', 
            'request_type', 
            'reason', 
            'status', 
            'adjusted_time', 
            'created_at', 
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status']

    def get_student(self, obj):
        """
        Return first_name and last_name from the CustomUser model via Student.user.
        """
        return {
            "first_name": obj.student.user.first_name,
            "last_name": obj.student.user.last_name,
            "phone_number": obj.student.user.phone_number,
        }