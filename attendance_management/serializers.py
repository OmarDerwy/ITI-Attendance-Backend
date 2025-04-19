from rest_framework import serializers
from .models import Schedule, Session, Student, Track, Branch, AttendanceRecord, PermissionRequest
from users.models import CustomUser
from datetime import datetime, timedelta

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
        """Get the start time from the first session of the day using prefetched data"""
        sessions = getattr(obj, 'prefetched_sessions', None)
        if sessions is None:
            sessions = obj.sessions.all()
        first_session = min(sessions, key=lambda s: s.start_time, default=None)
        return first_session.start_time if first_session else None
        
    def get_end_time(self, obj):
        """Get the end time from the last session of the day using prefetched data"""
        sessions = getattr(obj, 'prefetched_sessions', None)
        if sessions is None:
            sessions = obj.sessions.all()
        last_session = max(sessions, key=lambda s: s.end_time, default=None)
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
        Uses prefetched attendance_records if available.
        """
        attendance_records = getattr(obj, 'prefetched_attendance_records', None)
        if attendance_records is None:
            attendance_records = obj.attendance_records.all()
        total_students = len(attendance_records)
        attended_students = len({ar.student_id for ar in attendance_records if ar.check_in_time is not None})
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
    warning_status = serializers.SerializerMethodField()  # Added warning_status field


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
            'track_name',
            'warning_status',  # Added warning_status field
        ]

    def get_student(self, obj):
        """
        Return first_name and last_name from the CustomUser model via Student.user.
        """
        return {
            "first_name": obj.student.user.first_name,
            "last_name": obj.student.user.last_name
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

        # Prefetched permission requests for this student/schedule
        permission_requests_map = getattr(self, '_permission_requests_map', None)
        if permission_requests_map is None:
            # Build a map: {(schedule_id, student_id): [PermissionRequest, ...]}
            permission_requests = []
            # Try to get from context if provided
            if 'permission_requests' in self.context:
                permission_requests = self.context['permission_requests']
            else:
                permission_requests = PermissionRequest.objects.filter(schedule=schedule, student=student)
            permission_requests_map = {}
            for pr in permission_requests:
                key = (pr.schedule_id, pr.student_id)
                permission_requests_map.setdefault(key, []).append(pr)
            self._permission_requests_map = permission_requests_map

        prs = permission_requests_map.get((schedule.id, student.id), [])

        def get_permission(request_type):
            for pr in prs:
                if pr.request_type == request_type and pr.status == 'approved':
                    return pr
            return None

        day_excuse = get_permission('day_excuse')
        if day_excuse:
            return 'excused'

        if schedule.created_at > today:
            return 'pending'

        # Use prefetched sessions if available
        sessions = getattr(schedule, 'prefetched_sessions', None)
        if sessions is None:
            sessions = schedule.sessions.all()
        sessions = list(sessions)
        if not sessions:
            return 'no_sessions'
        first_session = min(sessions, key=lambda s: s.start_time, default=None)
        last_session = max(sessions, key=lambda s: s.end_time, default=None)
        if not first_session or not last_session:
            return 'no_sessions'

        grace_period = timedelta(minutes=15)
        check_in_deadline = first_session.start_time + grace_period

        late_permission = get_permission('late_check_in')
        early_leave_permission = get_permission('early_leave')
        early_leave_granted = early_leave_permission is not None

        if not obj.check_in_time:
            has_pending_permission = any(
                pr.status == 'pending' for pr in prs
            )
            if has_pending_permission:
                return 'pending'
            elif late_permission:
                if late_permission.adjusted_time and now <= late_permission.adjusted_time:
                    return 'excused_late'
                else:
                    return 'absent'
            else:
                return 'absent'

        # Check-in time evaluation
        if late_permission and late_permission.adjusted_time:
            is_on_time = obj.check_in_time <= late_permission.adjusted_time
            late_status = 'late-excused'
        else:
            is_on_time = obj.check_in_time <= check_in_deadline
            late_status = 'late-check-in'

        # Check-out is required except for day_excuse
        if not obj.check_out_time:
            if schedule.created_at == today and now.time() < last_session.end_time.time():
                return 'check-in' if is_on_time else f"{late_status}_active"
            else:
                return 'no-check-out' if is_on_time else f"{late_status}_no-check-out"

        # Check-out time evaluation
        if early_leave_granted:
            if obj.check_out_time >= late_permission.adjusted_time:
                return 'check-in_early-excused' if is_on_time else f"{late_status}_early-excused"
            return 'check-in_early-check-out' if is_on_time else f"{late_status}_early-check-out"
        elif obj.check_out_time < last_session.end_time:
            return 'check-in_early-check-out' if is_on_time else f"{late_status}_early-check-out"
        else:
            return 'attended' if is_on_time else late_status

    def get_adjusted_time(self, obj):
        """
        Calculate the adjusted time based on the prefetched permission requests.
        """
        # Use prefetched permission requests if available
        permission_requests_map = getattr(self, '_permission_requests_map', None)
        if permission_requests_map is None:
            return obj.check_in_time
        prs = permission_requests_map.get((obj.schedule_id, obj.student_id), [])
        for pr in prs:
            if pr.status == 'approved' and pr.adjusted_time:
                return pr.adjusted_time
        return obj.check_in_time

    def get_leave_request_status(self, obj):
        """
        Check if there is a pending leave request for the student and schedule using prefetched permission requests.
        """
        permission_requests_map = getattr(self, '_permission_requests_map', None)
        if permission_requests_map is None:
            return None
        prs = permission_requests_map.get((obj.schedule_id, obj.student_id), [])
        for pr in prs:
            if pr.status == 'pending':
                return 'pending'
        return None

    def get_track_name(self, obj):
        """
        Get the track name from the student object.
        """
        return obj.student.track.name if obj.student and obj.student.track else None
    
    def get_warning_status(self, obj):
        """
        Get the warning status ('excused' or 'unexcused') if a threshold is exceeded.
        Relies on the optimized Student.has_exceeded_warning_threshold() method.
        """
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

# Added StudentWithWarningSerializer
class StudentWithWarningSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    track_name = serializers.CharField(source='track.name', read_only=True)
    warning_type = serializers.SerializerMethodField()
    unexcused_absences = serializers.SerializerMethodField()
    excused_absences = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'track_name',
            'warning_type',
            'unexcused_absences',
            'excused_absences',
        ]

    def get_warning_type(self, obj):
        has_warning, warning_type = obj.has_exceeded_warning_threshold()
        return warning_type

    def get_unexcused_absences(self, obj):
        return obj.get_unexcused_absence_count()

    def get_excused_absences(self, obj):
        return obj.get_excused_absence_count()