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

        day_excuse = has_permission('day_excuse') #what if he atteneded the class?
        if day_excuse:
            return 'excused'

        if schedule.created_at > today:
            return 'pending'

        sessions = schedule.sessions.all()
        first_session = sessions.order_by('start_time').first()
        last_session = sessions.order_by('-end_time').first()

        if not first_session or not last_session:
            return 'no_sessions'

        grace_period = timedelta(minutes=15)
        check_in_deadline = first_session.start_time + grace_period

        late_permission = has_permission('late_check_in')
        early_leave_permission = has_permission('early_leave')
        early_leave_granted = early_leave_permission is not None

        if not obj.check_in_time:
            has_pending_permission = PermissionRequest.objects.filter(
                student=student,
                schedule=schedule,
                status='pending'
            ).exists()
            
            if has_pending_permission:
                return 'pending'
            elif late_permission:
                if late_permission.adjusted_time and now <= late_permission.adjusted_time: #no check-in 
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
            # If the student has early leave permission, check if the check-out time is before the adjusted time
            if obj.check_out_time >= late_permission.adjusted_time:
                return 'check-in_early-excused' if is_on_time else f"{late_status}_early-excused" 
            return 'check-in_early-check-out' if is_on_time else f"{late_status}_early-check-out"
        elif obj.check_out_time < last_session.end_time:
            return 'check-in_early-check-out' if is_on_time else f"{late_status}_early-check-out"
        else:
            return 'attended' if is_on_time else late_status
    
    
    def get_adjusted_time(self, obj): #used by DRF implicitly 
        """
        Calculate the adjusted time based on the permission request.
        """
        permission_request = PermissionRequest.objects.filter(
            student=obj.student, 
            schedule=obj.schedule, 
            status='approved'
        ).first()

        if permission_request:
            return permission_request.adjusted_time

        return obj.check_in_time
    def get_leave_request_status(self, obj):
        """
        Check if there is a pending leave request for the student and schedule.
        """
        pending_request = PermissionRequest.objects.filter(
            student=obj.student, 
            schedule=obj.schedule, 
        ).first()
        return pending_request.status if pending_request else None
    def get_track_name(self, obj):
        """
        Get the track name from the student object.
        """
        return obj.student.track.name if obj.student and obj.student.track else None
    
    # def to_representation(self, instance):
    #     data = super().to_representation(instance)
    #     if self.context.get('view').action == 'retrieve':
    #         # Include the schedule name in the response
    #         scheduleData = ScheduleSerializer(instance.schedule).data
    #         data['schedule'] = scheduleData
    #     return data

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