from rest_framework import serializers
from .models import LostItem, FoundItem, MatchedItem, ItemStatusChoices, Notification
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)

class LostItemSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    status = serializers.ChoiceField(choices=ItemStatusChoices.choices, read_only=True)

    class Meta:
        model = LostItem
        fields = ['item_id', 'name', 'description', 'status', 'place', 'lost_at', 'image', 'user']
        read_only_fields = ['item_id', 'lost_at']

class FoundItemSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    status = serializers.ChoiceField(choices=ItemStatusChoices.choices, read_only=True)

    class Meta:
        model = FoundItem
        fields = ['item_id', 'name', 'description', 'status', 'place', 'found_at', 'image', 'user']
        read_only_fields = ['item_id', 'found_at']

class MatchedItemSerializer(serializers.ModelSerializer):
    lost_item_details = LostItemSerializer(source='lost_item', read_only=True)
    found_item_details = FoundItemSerializer(source='found_item', read_only=True)
    lost_item = serializers.PrimaryKeyRelatedField(queryset=LostItem.objects.all(), write_only=True)
    found_item = serializers.PrimaryKeyRelatedField(queryset=FoundItem.objects.all(), write_only=True)
    status = serializers.ChoiceField(choices=MatchedItem.MatchingResult.choices)
    similarity_score = serializers.FloatField()
    lost_item_user = serializers.PrimaryKeyRelatedField(source='lost_item.user', read_only=True)
    found_item_user = serializers.PrimaryKeyRelatedField(source='found_item.user', read_only=True)

    class Meta:
        model = MatchedItem
        fields = ['match_id', 'lost_item', 'found_item', 'lost_item_details', 'found_item_details', 'similarity_score', 'created_at', 'status', 'lost_item_user', 'found_item_user']
        read_only_fields = ['match_id', 'created_at']


class ItemSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    status = serializers.ChoiceField(choices=ItemStatusChoices.choices, read_only=True)
    item_type = serializers.SerializerMethodField() # Lost or found item
    time_field = serializers.SerializerMethodField()  # Lost or found time

    class Meta:
        model = LostItem  # Placeholder, overridden in `to_representation`
        fields = ['item_id', 'name', 'description', 'status', 'place', 'image', 'user', 'item_type', 'time_field']
        read_only_fields = ['item_id']

    def get_item_type(self, obj):
        if isinstance(obj, LostItem):
            return 'lost'
        elif isinstance(obj, FoundItem):
            return 'found'
        return 'unknown'

    def get_time_field(self, obj):
        if isinstance(obj, LostItem):
            return obj.lost_at
        elif isinstance(obj, FoundItem):
            return obj.found_at
        return None

    def to_representation(self, instance):
        """Dynamically adjust the model and fields."""
        if isinstance(instance, FoundItem):
            self.Meta.model = FoundItem
        else:
            self.Meta.model = LostItem
        
        return super().to_representation(instance)

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'