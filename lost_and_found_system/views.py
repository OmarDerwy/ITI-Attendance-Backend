from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions
from .models import LostItem, FoundItem, MatchedItem
from .serializers import LostItemSerializer, FoundItemSerializer, MatchedItemSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.response import Response


class LostItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users to manage their lost items.
    """
    queryset = LostItem.objects.select_related('user').order_by('-lost_at')
    serializer_class = LostItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)  # Users only see their own items
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['GET'], url_path='my-items', url_name='my-lost-items')
    def my_lost_items(self, request):
        """
        Return the logged-in user's lost items.
        """
        user_lost_items = self.get_queryset().filter(user=self.request.user)
        page = self.paginate_queryset(user_lost_items)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(user_lost_items, many=True)
        return Response(serializer.data)


class FoundItemViewSet(viewsets.ModelViewSet):
    """
    API endpoint for users to manage their found items.
    """
    queryset = FoundItem.objects.select_related('user').order_by('-found_at')
    serializer_class = FoundItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(user=self.request.user)  # Users only see their own items
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['GET'], url_path='my-items', url_name='my-found-items')
    def my_found_items(self, request):
        """
        Return the logged-in user's found items.
        """
        user_found_items = self.get_queryset().filter(user=self.request.user)
        page = self.paginate_queryset(user_found_items)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(user_found_items, many=True)
        return Response(serializer.data)


class MatchedItemViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint to view and confirm matched items (Read-Only).
    """
    queryset = MatchedItem.objects.select_related('lost_item__user', 'found_item__user').order_by('-created_at')
    serializer_class = MatchedItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination

    def get_queryset(self):
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(lost_item__user=self.request.user)
        return qs

    @action(detail=False, methods=['GET'], url_path='my-matches', url_name='my-matches')
    def my_matches(self, request):
        """
        Return matched items related to the logged-in user's lost items.
        """
        user_matches = self.get_queryset()
        page = self.paginate_queryset(user_matches)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(user_matches, many=True)
        return Response(serializer.data)

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
