from django.apps import AppConfig


class AttendanceManagementConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attendance_management'

    def ready(self):
        """
        Connect signal handlers when the app is ready
        """
        # Import signals module to register signal handlers
        import attendance_management.signals
        return super().ready()
