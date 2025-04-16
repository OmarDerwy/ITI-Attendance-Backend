from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.conf import settings
from django.core.cache import cache
import json
import os
from ..utils import get_setting, set_setting
from ..settings_models import ApplicationSetting

@api_view(['GET'])
@permission_classes([IsAdminUser])
def get_absence_thresholds(request):
    """
    Get the current warning thresholds for both excused and unexcused absences for both program types.
    Only accessible by admin users.
    """
    try:
        thresholds = {
            'nine_months': {
                'unexcused': ApplicationSetting.get_unexcused_absence_threshold('nine_months'),
                'excused': ApplicationSetting.get_excused_absence_threshold('nine_months')
            },
            'intensive': {
                'unexcused': ApplicationSetting.get_unexcused_absence_threshold('intensive'),
                'excused': ApplicationSetting.get_excused_absence_threshold('intensive')
            }
        }
        return Response(thresholds, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def update_absence_thresholds(request):
    """
    Update the warning thresholds for both excused and unexcused absences for a specific program type.
    Only accessible by admin users.
    
    Request body should contain:
    - program_type: Either 'nine_months' or 'intensive'
    - unexcused_threshold: New threshold value for unexcused absences (positive integer)
    - excused_threshold: New threshold value for excused absences (positive integer)
    """
    try:
        data = request.data
        program_type = data.get('program_type')
        
        if program_type not in ['nine_months', 'intensive']:
            return Response(
                {'error': 'Invalid program type. Must be either "nine_months" or "intensive"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        unexcused_threshold = data.get('unexcused_threshold')
        excused_threshold = data.get('excused_threshold')

        if unexcused_threshold is None or excused_threshold is None:
            return Response(
                {'error': 'Missing threshold values in request body'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            unexcused_threshold = int(unexcused_threshold)
            excused_threshold = int(excused_threshold)
        except ValueError:
            return Response(
                {'error': 'Thresholds must be positive integers'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if unexcused_threshold < 0 or excused_threshold < 0:
            return Response(
                {'error': 'Thresholds must be non-negative integers'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the settings in the database
        if unexcused_threshold is not None:
            key = 'unexcused_absence_threshold_intensive' if program_type == 'intensive' else 'unexcused_absence_threshold'
            set_setting(
                key, 
                unexcused_threshold,
                f'Number of unexcused absences after which a student receives a warning ({program_type} program)'
            )

        if excused_threshold is not None:
            key = 'excused_absence_threshold_intensive' if program_type == 'intensive' else 'excused_absence_threshold'
            set_setting(
                key, 
                excused_threshold,
                f'Number of excused absences after which a student receives a warning ({program_type} program)'
            )
        
        return Response({
            'message': 'Absence thresholds updated successfully',
            'program_type': program_type,
            'unexcused_threshold': unexcused_threshold,
            'excused_threshold': excused_threshold
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {'error': f'Error updating absence thresholds: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 