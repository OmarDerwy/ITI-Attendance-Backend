from rest_framework import serializers
from .models import LostItem, FoundItem, MatchedItem, ItemStatusChoices

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

    class Meta:
        model = MatchedItem
        fields = ['match_id', 'lost_item', 'found_item', 'similarity_score', 'created_at', 'status']
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
