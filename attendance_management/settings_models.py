from django.db import models

class ApplicationSetting(models.Model):
    """
    Model to store application-wide settings.
    This is used for settings that need to be configurable through the UI
    but should persist across deployments.
    """
    key = models.CharField(max_length=50, unique=True)
    value = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Application Setting"
        verbose_name_plural = "Application Settings"
    
    def __str__(self):
        return f"{self.key}: {self.value}"

    @classmethod
    def get_unexcused_absence_threshold(cls, program_type='nine_months'):
        """
        Get the unexcused absence threshold based on program type.
        Default is for 9-month program.
        """
        key = 'unexcused_absence_threshold_intensive' if program_type == 'intensive' else 'unexcused_absence_threshold'
        setting = cls.objects.filter(key=key).first()
        return int(setting.value) if setting else 3

    @classmethod
    def get_excused_absence_threshold(cls, program_type='nine_months'):
        """
        Get the excused absence threshold based on program type.
        Default is for 9-month program.
        """
        key = 'excused_absence_threshold_intensive' if program_type == 'intensive' else 'excused_absence_threshold'
        setting = cls.objects.filter(key=key).first()
        return int(setting.value) if setting else 3 