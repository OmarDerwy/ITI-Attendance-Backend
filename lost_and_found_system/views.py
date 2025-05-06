from itertools import chain
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions
from .models import LostItem, FoundItem, MatchedItem, Notification, ItemStatusChoices
from .serializers import LostItemSerializer, FoundItemSerializer, MatchedItemSerializer, ItemSerializer, NotificationSerializer
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging
from .utils import match_lost_and_found_items, send_and_save_notification
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import models  # Add this import for Q objects
from rest_framework import filters
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AllItemsViewSet(viewsets.ModelViewSet):
    """
    API endpoint to view all lost and found items.
    """
    serializer_class = ItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    logger.info("AllItemsViewSet initialized")

    def get_queryset(self):
        
        if not self.request.user.is_staff:
            LostItems = LostItem.objects.filter(user = self.request.user)
            FoundItems = FoundItem.objects.filter(user = self.request.user)
        else:
            LostItems = LostItem.objects.all()
            FoundItems = FoundItem.objects.all()
        return list(chain(LostItems, FoundItems))

class LostItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users to manage their lost items.
    """
    queryset = LostItem.objects.select_related('user').order_by('-lost_at')
    serializer_class = LostItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'place']

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)  # Users only see their own items
        return qs

    def perform_create(self, serializer):
        logger.info("perform_create method called.")
        # Save the lost item
        lost_item = serializer.save(user=self.request.user)
        logger.info(f"LostItem created: {lost_item}")
        
        # Process matching asynchronously
        # Import here to avoid circular imports
        from django.db import transaction
        import threading
        
        def background_matching():
            logger.info(f"Starting background matching for LostItem: {lost_item.name}")
            # Match the lost item with all found items
            found_items = FoundItem.objects.filter(status=ItemStatusChoices.FOUND)
            logger.info(f"Matching LostItem with {found_items.count()} FoundItems")
            
            with transaction.atomic():
                for found_item in found_items:
                    match_result = match_lost_and_found_items(lost_item, found_item)
                    
                    if match_result:
                        logger.info(f"Match created: {match_result}")
                        
                        # Update status after match is created - use refresh_from_db to ensure we have latest data
                        lost_item.refresh_from_db()
                        found_item.refresh_from_db()
                        
                        # Update both items to MATCHED status
                        lost_item.status = ItemStatusChoices.MATCHED
                        found_item.status = ItemStatusChoices.MATCHED
                        
                        # Force save with update_fields to ensure only status is updated
                        lost_item.save(update_fields=['status'])
                        found_item.save(update_fields=['status'])
                        
                        logger.info(f"Updated status of Lost item '{lost_item.name}' to {lost_item.status}")
                        logger.info(f"Updated status of Found item '{found_item.name}' to {found_item.status}")
                    else:
                        logger.info(f"No match found between LostItem '{lost_item.name}' and FoundItem '{found_item.name}'")
            
            logger.info(f"Background matching completed for LostItem: {lost_item.name}")
        
        # Start the matching process in a background thread
        matching_thread = threading.Thread(target=background_matching)
        matching_thread.daemon = True  # Thread will exit when main program exits
        matching_thread.start()
        
        logger.info(f"Item created and background matching initiated, returning response immediately")

class FoundItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users to manage their found items.
    """
    queryset = FoundItem.objects.select_related('user').order_by('-found_at')
    serializer_class = FoundItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description', 'place']

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)  # Users only see their own items
        return qs

    def perform_create(self, serializer):
        logger.info("perform_create method called.")
        # Save the found item
        found_item = serializer.save(user=self.request.user)
        logger.info(f"FoundItem created: {found_item}")
        
        # Process matching asynchronously
        # Import here to avoid circular imports
        from django.db import transaction
        import threading
        
        def background_matching():
            logger.info(f"Starting background matching for FoundItem: {found_item.name}")
            # Match the found item with all lost items
            lost_items = LostItem.objects.filter(status=ItemStatusChoices.LOST)
            logger.info(f"Matching FoundItem with {lost_items.count()} LostItems")
            
            with transaction.atomic():
                for lost_item in lost_items:
                    match_result = match_lost_and_found_items(lost_item, found_item)
                    
                    if match_result:
                        logger.info(f"Match created: {match_result}")
                        
                        # Update status after match is created - use refresh_from_db to ensure we have latest data
                        lost_item.refresh_from_db()
                        found_item.refresh_from_db()
                        
                        # Update both items to MATCHED status
                        lost_item.status = ItemStatusChoices.MATCHED
                        found_item.status = ItemStatusChoices.MATCHED
                        
                        # Force save with update_fields to ensure only status is updated
                        lost_item.save(update_fields=['status'])
                        found_item.save(update_fields=['status'])
                        
                        logger.info(f"Updated status of Lost item '{lost_item.name}' to {lost_item.status}")
                        logger.info(f"Updated status of Found item '{found_item.name}' to {found_item.status}")
                    else:
                        logger.info(f"No match found between LostItem '{lost_item.name}' and FoundItem '{found_item.name}'")
            
            logger.info(f"Background matching completed for FoundItem: {found_item.name}")
        
        # Start the matching process in a background thread
        matching_thread = threading.Thread(target=background_matching)
        matching_thread.daemon = True  # Thread will exit when main program exits
        matching_thread.start()
        
        logger.info(f"Item created and background matching initiated, returning response immediately")

    @action(detail=False, methods=['GET'])
    def my_found_items(self, request):
        user_found_items = self.get_queryset().filter(user=self.request.user)
        page = self.paginate_queryset(user_found_items)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(user_found_items, many=True)
        return Response(serializer.data)


class MatchedItemPagination(PageNumberPagination):
    page_size = 3
    page_size_query_param = 'page_size'
    max_page_size = 10

class MatchedItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint to view and confirm matched items (Read-Only).
    """
    queryset = MatchedItem.objects.select_related('lost_item__user', 'found_item__user').order_by('-created_at')
    serializer_class = MatchedItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = MatchedItemPagination  # Use the custom pagination class

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            # Users can see matches where they are either the lost item owner or found item owner
            qs = qs.filter(
                models.Q(lost_item__user=self.request.user) | 
                (models.Q(found_item__user=self.request.user) & models.Q(status=MatchedItem.MatchingResult.SUCCEEDED))
            )
        return qs

    @action(detail=True, methods=['POST'], url_path='confirm-match', url_name='confirm-match')
    def confirm_match(self, request, pk=None):
        """
        Allow the owner of the lost item to confirm if a match is valid.
        """
        match = get_object_or_404(MatchedItem, pk=pk)
        # only the lost item owner or admin can confirm the match
        if match.lost_item.user != request.user or request.user.is_staff:
            return Response({"error": "You are not authorized to confirm this match."}, status=403)

        new_status = request.data.get('status')
        valid_statuses = dict(MatchedItem.MatchingResult.choices)

        if new_status not in valid_statuses:
            return Response({"error": "Invalid status provided."}, status=400)

        match.status = new_status
        match.save()
        return Response({"message": "Match status updated successfully."})

    @action(detail=True, methods=['POST'], url_path='update-status', url_name='update-status')
    def update_status(self, request, pk=None):
        """
        Allow the user to update the status of a MatchedItem from FAILED to SUCCEEDED
        and notify the user who submitted the FoundItem in real-time.
        """
        match = get_object_or_404(MatchedItem, pk=pk)

        # Ensure the user is authorized to update the status
        if match.lost_item.user != request.user:
            return Response({"error": "You are not authorized to update this match."}, status=403)

        # Check the current status
        if match.status != MatchedItem.MatchingResult.FAILED:
            return Response({"error": "Only matches with status 'FAILED' can be updated."}, status=400)

        # Update the status to SUCCEEDED
        match.status = MatchedItem.MatchingResult.SUCCEEDED
        match.save()
        
        # Update both lost and found items to CONFIRMED status
        lost_item = match.lost_item
        found_item = match.found_item
        
        lost_item.status = ItemStatusChoices.CONFIRMED
        found_item.status = ItemStatusChoices.CONFIRMED
        
        lost_item.save(update_fields=['status'])
        found_item.save(update_fields=['status'])
        
        logger.info(f"Updated lost item {lost_item.name} status to CONFIRMED")
        logger.info(f"Updated found item {found_item.name} status to CONFIRMED")

        # Notify the user who submitted the FoundItem
        found_item_user = match.found_item.user
        notification_message = (
            f"Congratulations! We found the owner of the item you submitted: '{match.found_item.name}'. "
            f"The owner's name is {match.lost_item.user}. (Match ID: {match.match_id})"
        )
        # Use the utility function instead of separate operations
        send_and_save_notification(
            user=found_item_user,
            title="Owner Found!",
            message=notification_message,
            match_id=match.match_id  # Pass match_id to the utility function
        )
        return Response({
            "message": "Match status updated to SUCCEEDED and item statuses updated to CONFIRMED.",
            "notification": notification_message,
            "lost_item_status": lost_item.status,
            "found_item_status": found_item.status,
        })

    @action(detail=True, methods=['POST'], url_path='decline-match', url_name='decline-match')
    def decline_match(self, request, pk=None):
        """
        Decline a match, revert items to their original status, and delete the match record.
        Only the lost item owner or admin can decline a match.
        
        Requires only the matched_item ID (from URL).
        """
        # Get the matched item using the ID from the URL
        match = get_object_or_404(MatchedItem, pk=pk)
        
        # Check if user is authorized (lost item owner or admin)
        if match.lost_item.user != request.user and not request.user.is_staff:
            return Response({
                "error": "You are not authorized to decline this match."
            }, status=403)

        # Store data for response before deletion
        lost_item_name = match.lost_item.name
        found_item_name = match.found_item.name
        lost_item_id = match.lost_item.item_id
        found_item_id = match.found_item.item_id
        
        # Get references to both items
        lost_item = match.lost_item
        found_item = match.found_item
        
        # Revert the lost item status back to LOST
        lost_item.status = ItemStatusChoices.LOST
        lost_item.save(update_fields=['status'])
        
        # Revert the found item status back to FOUND
        found_item.status = ItemStatusChoices.FOUND
        found_item.save(update_fields=['status'])
        
        # Delete the match record
        match.delete()
        
        # Notify the found item user that the match was declined
        if found_item.user != request.user:
            notification_message = (
                f"The owner of '{lost_item_name}' has declined the match with your found item '{found_item_name}'. "
                f"Your item has been returned to the active found items list."
            )
            
            send_and_save_notification(
                user=found_item.user,
                title="Match Declined",
                message=notification_message
            )
        
        return Response({
            "message": "Match has been declined successfully.",
            "details": {
                "lost_item": {
                    "id": lost_item_id,
                    "name": lost_item_name,
                    "status": lost_item.status
                },
                "found_item": {
                    "id": found_item_id,
                    "name": found_item_name,
                    "status": found_item.status
                }
            }
        }, status=200)

class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes=[IsAuthenticated]
    pagination_class = None  # Remove pagination for this viewset

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    
    @action(detail=False, methods=["GET"])
    def unread(self, request):
        """Get unread notifications"""
        unread_notifications = self.get_queryset().filter(is_read=False)
        serializer = self.get_serializer(unread_notifications, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["POST"])
    def mark_as_read(self, request, pk=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "Notification marked as read"})
    
    @action(detail=False, methods=["POST"])
    def mark_all_as_read(self, request):
        """Mark all notifications as read for the user"""
        self.get_queryset().update(is_read=True)
        return Response({"status": "All notifications marked as read"})