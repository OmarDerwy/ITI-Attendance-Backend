from django.db import models

class ApplicationSetting(models.Model):
    """
    Model to store application-wide settings.
    This is used for settings that need to be configurable through the UI
    but should persist across deployments.
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Application Setting"
        verbose_name_plural = "Application Settings"
    
    def __str__(self):
        return f"{self.key}: {self.value}"

    @classmethod
    def get_unexcused_absence_threshold(cls):
        """Get the threshold for unexcused absences"""
        try:
            setting = cls.objects.get(key='unexcused_absence_threshold')
            return setting.value
        except cls.DoesNotExist:
            return 3  # Default value

    @classmethod
    def get_excused_absence_threshold(cls):
        """Get the threshold for excused absences"""
        try:
            setting = cls.objects.get(key='excused_absence_threshold')
            return setting.value
        except cls.DoesNotExist:
            return 3  # Default value 