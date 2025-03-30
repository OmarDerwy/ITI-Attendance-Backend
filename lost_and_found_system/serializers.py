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
    lost_item = LostItemSerializer(read_only=True)
    found_item = FoundItemSerializer(read_only=True)
    status = serializers.ChoiceField(choices=MatchedItem.MatchingResult.choices)
    similarity_score = serializers.FloatField(read_only=True)

    class Meta:
        model = MatchedItem
        fields = ['match_id', 'lost_item', 'found_item', 'similarity_score', 'created_at', 'status']
        read_only_fields = ['match_id', 'created_at']

    def create(self, validated_data):
        # Create the MatchedItem instance
        matched_item = super().create(validated_data)

        # Send a real-time notification if the similarity score exceeds the threshold
        if matched_item.similarity_score > 70:
            channel_layer = get_channel_layer()
            group_name = f"user_{matched_item.lost_item.user.id}" if matched_item.lost_item.user.is_authenticated else "anonymous"
            message = {
                "type": "send_notification",
                "message": {
                    "title": "Item Matched!",
                    "body": f"Your lost item '{matched_item.lost_item.name}' has been matched with a found item '{matched_item.found_item.name}' with a similarity score of {matched_item.similarity_score:.2f}%."
                }
            }
            logger.info(f"Sending notification to group: {group_name} with message: {message}")
            async_to_sync(channel_layer.group_send)(group_name, message)

        return matched_item

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