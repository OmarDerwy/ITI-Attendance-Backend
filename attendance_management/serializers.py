from rest_framework import serializers
from .models import Schedule, Session, Student, Track, Branch

class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['id', 'title', 'start_time', 'end_time', 'session_type', 'schedule']

class ScheduleSerializer(serializers.ModelSerializer):
    sessions = SessionSerializer(many=True, read_only=True)

    class Meta:
        model = Schedule
        fields = ['id', 'name', 'track', 'created_at', 'sessions']

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ['id', 'user', 'track']

class TrackSerializer(serializers.ModelSerializer):
    branch = serializers.StringRelatedField()

    class Meta:
        model = Track
        fields = ['id', 'name', 'supervisor', 'intake', 'start_date', 'description', 'branch']

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ['id', 'name', 'latitude', 'longitude', 'location_url', 'radius']