from rest_framework import serializers
from .models import Schedule, Session, Student, Track, Branch, AttendanceRecord, PermissionRequest

class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['id', 'title', 'start_time', 'end_time', 'session_type', 'schedule']

class ScheduleSerializer(serializers.ModelSerializer):
    sessions = SessionSerializer(many=True, read_only=True)

    class Meta:
        model = Schedule
        fields = ['id', 'name', 'track', 'created_at', 'sessions', 'custom_branch']

class StudentSerializer(serializers.ModelSerializer):  # Updated to use Student
    class Meta:
        model = Student
        fields = ['id', 'user', 'track']

class TrackSerializer(serializers.ModelSerializer):
    branch_id = serializers.IntegerField(source='default_branch.id', read_only=True)
    track_id = serializers.IntegerField(source='id', read_only=True)
    default_branch = serializers.StringRelatedField()
    supervisor = serializers.SerializerMethodField()  # Get the supervisor's first and last name

    def get_supervisor(self, obj):
        if obj.supervisor:
            return f"{obj.supervisor.first_name} {obj.supervisor.last_name} "
        return None
    program_type = serializers.CharField(source='get_program_type_display', read_only=True)
    class Meta:
        model = Track
        fields = '__all__'  # Ensure branch_id and track_id are included

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