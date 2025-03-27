from django.contrib.auth.models import Group
from rest_framework.response import Response
def getGroupIDFromNames(groups):
    if not groups:
        return Response({'message': 'No groups provided in the request'}, status=400)
    group_ids = []
    for group_name in groups:
        try:
            group = Group.objects.get(name=group_name)
            group_ids.append(group.id)
        except Group.DoesNotExist:
            return Response({'message': f'Group "{group_name}" does not exist'}, status=400)
    return group_ids