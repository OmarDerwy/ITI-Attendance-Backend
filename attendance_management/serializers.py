from rest_framework import serializers
from .models import Schedule, Session, Student, Track, Branch, AttendanceRecord, PermissionRequest
from users.models import CustomUser

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
    
    class Meta:
        model = Schedule
        fields = ['id','name', 'track', 'created_at', 'sessions', 'custom_branch', 'is_shared', 'start_time', 'end_time']

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
    class Meta:
        model = AttendanceRecord
        fields = ['id', 'student', 'schedule', 'check_in_time', 'check_out_time', 'excuse', 'early_leave', 'late_check_in']

class PermissionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionRequest
        fields = ['id', 'student', 'schedule', 'request_type', 'reason', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'status']