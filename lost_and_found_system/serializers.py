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
