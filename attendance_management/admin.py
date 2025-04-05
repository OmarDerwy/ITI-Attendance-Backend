from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Branch, Track, Schedule, Session,Student, AttendanceRecord, PermissionRequest

# Register your models here.
admin.site.register(Branch)
admin.site.register(Track)
admin.site.register(Session)
admin.site.register(Student)
admin.site.register(AttendanceRecord)
admin.site.register(PermissionRequest)

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'track', 'created_at', 'custom_branch', 'is_shared')
    list_filter = ('track', 'created_at', 'is_shared')
    search_fields = ('name', 'track__name')
