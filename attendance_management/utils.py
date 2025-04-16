from .settings_models import ApplicationSetting

def get_setting(key, default=None):
    """
    Get an application setting by key.
    
    Args:
        key (str): The key of the setting to retrieve
        default: The default value to return if the setting doesn't exist
        
    Returns:
        The value of the setting, or the default if not found
    """
    try:
        setting = ApplicationSetting.objects.get(key=key)
        return setting.value
    except ApplicationSetting.DoesNotExist:
        return default

def set_setting(key, value, description=""):
    """
    Set an application setting.
    
    Args:
        key (str): The key of the setting to set
        value: The value to set (will be stored as JSON)
        description (str): A description of the setting
        
    Returns:
        The ApplicationSetting instance
    """
    setting, created = ApplicationSetting.objects.update_or_create(
        key=key,
        defaults={
            'value': value,
            'description': description
        }
    )
    return setting 