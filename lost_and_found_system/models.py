from django.db import models
from users.models import CustomUser
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import logging

logger = logging.getLogger(__name__)

class ItemStatusChoices(models.TextChoices):
    LOST = 'LOST', 'Lost'
    FOUND = 'FOUND', 'Found'
    MATCHED = 'MATCHED', 'Matched'
    CONFIRMED = 'CONFIRMED', 'Confirmed'  # New status for confirmed matches

class LostItem(models.Model):
    item_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=ItemStatusChoices.choices,
        default=ItemStatusChoices.LOST
    )
    place = models.CharField(max_length=100)
    lost_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='lost_item_images/', blank=True, null=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='lost_items')

    def __str__(self):
        return f"{self.name} (Lost)"

    class Meta:
        indexes = [models.Index(fields=['status', 'lost_at'])]

class FoundItem(models.Model):
    item_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=ItemStatusChoices.choices,
        default=ItemStatusChoices.FOUND
    )
    place = models.CharField(max_length=100)
    found_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='found_item_images/', blank=True, null=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='found_items')

    def __str__(self):
        return f"{self.name} (Found)"

    class Meta:
        indexes = [models.Index(fields=['status', 'found_at'])]

class MatchedItem(models.Model):
    class MatchingResult(models.TextChoices):
        SUCCEEDED = 'SUCCEEDED', 'Succeeded'
        FAILED = 'FAILED', 'Failed'

    match_id = models.AutoField(primary_key=True)
    lost_item = models.ForeignKey(LostItem, on_delete=models.PROTECT, related_name='matched_lost')
    found_item = models.ForeignKey(FoundItem, on_delete=models.PROTECT, related_name='matched_found')
    similarity_score = models.FloatField()  # Similarity for better matching logic
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)  # When the user confirms the match
    status = models.CharField(
        max_length=10,
        choices=MatchingResult.choices,
        default=MatchingResult.FAILED
    )

    def __str__(self):
        return f"Match: {self.lost_item.name} ↔ {self.found_item.name}"

    class Meta:
        indexes = [models.Index(fields=['lost_item', 'found_item'])]
        constraints = [
            models.UniqueConstraint(fields=['lost_item', 'found_item'], name='unique_match')
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.similarity_score > 70:
            channel_layer = get_channel_layer()
            group_name = f"user_{self.lost_item.user.id}" if self.lost_item.user.is_authenticated else "anonymous"
            message = {
                "type": "send_notification",
                "message": {
                    "title": "Item Matched!",
                    "body": f"Your lost item '{self.lost_item.name}' has been matched with a found item '{self.found_item.name}' with a similarity score of {self.similarity_score:.2f}%."
                }
            }
            logger.info(f"Sending notification to group: {group_name} with message: {message}")
            async_to_sync(channel_layer.group_send)(group_name, message)

class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="notifications")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"