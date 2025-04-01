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
    branch = serializers.StringRelatedField()

    class Meta:
        model = Track
        fields = ['id', 'name', 'supervisor', 'intake', 'start_date', 'description', 'default_branch']

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