from django.db import models
from users.models import CustomUser

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