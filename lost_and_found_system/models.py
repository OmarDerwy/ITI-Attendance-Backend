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
    CONFIRMED = 'CONFIRMED', 'Confirmed' 

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
    image = models.URLField(max_length=500, verbose_name='Image URL', blank=True, null=True)
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
    image = models.URLField(max_length=500, verbose_name='Image URL', blank=True, null=True)
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
        # Check if this is a new instance being created (not an update)
        is_new = self.pk is None
        
        # Save the instance
        super().save(*args, **kwargs)
        
        # Only send notification if this is a new instance and similarity score exceeds threshold
        if is_new and self.similarity_score > 60:
            # Create notification message
            notification_message = f"Your lost item '{self.lost_item.name}' has been matched with a found item '{self.found_item.name}' with a similarity score of {self.similarity_score:.2f}%."
            
            # Use the utility function to send and save notification
            from .utils import send_and_save_notification  # Import here to avoid circular imports
            send_and_save_notification(
                user=self.lost_item.user,
                title="Item Matched!",
                message=notification_message,
                match_id=self.match_id
            )

class Notification(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="notifications")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    matched_item = models.ForeignKey(MatchedItem, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"