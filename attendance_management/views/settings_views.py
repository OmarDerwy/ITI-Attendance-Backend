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
    Get the current warning thresholds for both excused and unexcused absences.
    Only accessible by admin users.
    """
    unexcused_threshold = ApplicationSetting.get_unexcused_absence_threshold()
    excused_threshold = ApplicationSetting.get_excused_absence_threshold()
    
    return Response({
        'unexcused_threshold': unexcused_threshold,
        'excused_threshold': excused_threshold
    })

@api_view(['POST'])
@permission_classes([IsAdminUser])
def update_absence_thresholds(request):
    """
    Update the warning thresholds for both excused and unexcused absences.
    Only accessible by admin users.
    
    Request body should contain:
    - unexcused_threshold: New threshold value for unexcused absences (positive integer)
    - excused_threshold: New threshold value for excused absences (positive integer)
    """
    try:
        unexcused_threshold = request.data.get('unexcused_threshold')
        excused_threshold = request.data.get('excused_threshold')
        
        if unexcused_threshold is None or excused_threshold is None:
            return Response(
                {'error': 'Missing threshold values in request body'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate that the thresholds are positive integers
        unexcused_threshold = int(unexcused_threshold)
        excused_threshold = int(excused_threshold)
        
        if unexcused_threshold <= 0 or excused_threshold <= 0:
            return Response(
                {'error': 'Thresholds must be positive integers'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the settings in the database
        set_setting(
            'unexcused_absence_threshold', 
            unexcused_threshold,
            'Number of unexcused absences after which a student receives a warning'
        )
        
        set_setting(
            'excused_absence_threshold', 
            excused_threshold,
            'Number of excused absences after which a student receives a warning'
        )
        
        return Response({
            'message': 'Absence thresholds updated successfully',
            'unexcused_threshold': unexcused_threshold,
            'excused_threshold': excused_threshold
        })
    
    except ValueError:
        return Response(
            {'error': 'Thresholds must be positive integers'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Error updating absence thresholds: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 