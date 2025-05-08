from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Count, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from calendar import monthrange
from collections import defaultdict
import calendar
from ..models import Track, Schedule, Session
from ..serializers import TrackSerializer
from core import permissions


class TrackViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsSupervisorOrAboveUser]
    serializer_class = TrackSerializer
    pagination_class = None 

    def get_queryset(self):
        user = self.request.user
        user_groups = user.groups.values_list('name', flat=True)
        queryset = Track.objects.select_related('default_branch', 'supervisor')
        program_type = self.request.query_params.get('program_type')
        is_active = self.request.query_params.get('is_active')
        if program_type:
            queryset = queryset.filter(program_type=program_type)
        if is_active:
            is_active = is_active.lower() == 'true' if is_active else False
            queryset = queryset.filter(is_active=is_active)
        if 'admin' in user_groups:
            return queryset
        if 'coordinator' in user_groups or 'branch-manager' in user_groups:
            coordinator_profile = user.coordinator
            return queryset.filter(default_branch__coordinators=coordinator_profile)
        if 'supervisor' in user_groups:
            return queryset.filter(supervisor=user)
        return Track.objects.none()  # No access for other users
    
    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsSupervisorOrAboveUser])
    def archive_track(self, request, pk=None):
        """
        Archive a track.
        """
        track = self.get_object()
        track.is_active = False
        track.save()
        return Response({'status': 'Track archived successfully.'}, status=200)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsBranchManagerOrAboveUser])
    def branch_statistics(self, request):
        """
        Get all tracks for a specific branch with online/offline statistics.
        
        Query Parameters:
        - branch_id: ID of the branch to filter tracks
        - start_date: Optional start date for statistics (YYYY-MM-DD)
        - end_date: Optional end date for statistics (YYYY-MM-DD)
        - is_active: Optional filter for active/inactive tracks (true/false)
        
        Returns:
        - List of tracks with their online/offline statistics
        - Each track includes daily data and monthly summaries
        - Track details including start_date, intake, supervisor, and description
        """
        branch_id = request.query_params.get('branch_id')
        if not branch_id:
            return Response({"error": "branch_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get date range parameters with defaults
        today = timezone.now().date()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        is_active_str = request.query_params.get('is_active')
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today - timedelta(days=90)
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get tracks for the specified branch
        tracks_query = Track.objects.filter(
            Q(default_branch_id=branch_id) | 
            Q(schedules__custom_branch_id=branch_id)
        ).distinct().select_related('supervisor', 'default_branch')
        
        # Apply is_active filter if provided
        if is_active_str is not None:
            is_active = is_active_str.lower() == 'true'
            tracks_query = tracks_query.filter(is_active=is_active)
        
        tracks = tracks_query
        
        result = []
        
        for track in tracks:
            # Get all schedules for this track within date range
            schedules = Schedule.objects.filter(
                track=track,
                created_at__gte=start_date,
                created_at__lte=end_date
            ).prefetch_related('sessions')
            
            # Initialize data structures
            daily_data = {}
            monthly_stats = defaultdict(lambda: {'online_days': 0, 'offline_days': 0, 'total_days': 0})
            
            # Process each schedule
            for schedule in schedules:
                date_str = schedule.created_at.strftime('%Y-%m-%d')
                month_key = schedule.created_at.strftime('%Y-%m')
                
                # Check if any session for this schedule is offline
                has_offline_session = schedule.sessions.filter(session_type='offline').exists()
                session_type = 'offline' if has_offline_session else 'online'
                
                # Store daily data
                daily_data[date_str] = {
                    'date': date_str,
                    'type': session_type,
                    'schedule_id': schedule.id,
                    'schedule_name': schedule.name
                }
                
                # Update monthly statistics
                if session_type == 'online':
                    monthly_stats[month_key]['online_days'] += 1
                else:
                    monthly_stats[month_key]['offline_days'] += 1
                monthly_stats[month_key]['total_days'] += 1
            
            # Calculate percentages for monthly stats
            monthly_summary = []
            for month_key, stats in monthly_stats.items():
                year, month = map(int, month_key.split('-'))
                month_name = calendar.month_name[month]
                
                online_percentage = 0
                offline_percentage = 0
                
                if stats['total_days'] > 0:
                    online_percentage = round((stats['online_days'] / stats['total_days']) * 100, 2)
                    offline_percentage = round((stats['offline_days'] / stats['total_days']) * 100, 2)
                
                monthly_summary.append({
                    'year': year,
                    'month': month,
                    'month_name': month_name,
                    'online_days': stats['online_days'],
                    'offline_days': stats['offline_days'],
                    'total_days': stats['total_days'],
                    'online_percentage': online_percentage,
                    'offline_percentage': offline_percentage
                })
            
            # Sort monthly summary by year and month
            monthly_summary.sort(key=lambda x: (x['year'], x['month']))
            
            # Sort daily data by date
            daily_data_sorted = [daily_data[date_key] for date_key in sorted(daily_data.keys())]
            
            # Calculate overall statistics
            total_days = len(daily_data)
            online_days = sum(1 for day in daily_data.values() if day['type'] == 'online')
            offline_days = sum(1 for day in daily_data.values() if day['type'] == 'offline')
            
            online_percentage = 0
            offline_percentage = 0
            
            if total_days > 0:
                online_percentage = round((online_days / total_days) * 100, 2)
                offline_percentage = round((offline_days / total_days) * 100, 2)
            
            # Format supervisor name
            supervisor_name = None
            if track.supervisor:
                supervisor_name = f"{track.supervisor.first_name} {track.supervisor.last_name}"
            
            # Format start_date
            formatted_start_date = track.start_date.strftime('%Y-%m-%d') if track.start_date else None
            
            # Add track data to result with additional fields
            result.append({
                'track_id': track.id,
                'track_name': track.name,
                'program_type': track.program_type,
                'program_type_display': track.get_program_type_display(),
                'is_active': track.is_active,
                'start_date': formatted_start_date,
                'intake': track.intake,
                'supervisor': supervisor_name,
                'supervisor_id': track.supervisor.id if track.supervisor else None,
                'description': track.description,
                'default_branch': track.default_branch.name if track.default_branch else None,
                'default_branch_id': track.default_branch.id if track.default_branch else None,
                'statistics': {
                    'total_days': total_days,
                    'online_days': online_days,
                    'offline_days': offline_days,
                    'online_percentage': online_percentage,
                    'offline_percentage': offline_percentage,
                    'monthly_summary': monthly_summary
                },
                'daily_data': daily_data_sorted
            })
        
        return Response(result)
