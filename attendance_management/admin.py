from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Branch, Track, Schedule, Session, Student, AttendanceRecord, PermissionRequest, ApplicationSetting

# Register your models here.
admin.site.register(Branch)
admin.site.register(Track)
admin.site.register(Session)
admin.site.register(PermissionRequest)
admin.site.register(ApplicationSetting)

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'track', 'created_at', 'custom_branch', 'is_shared')
    list_filter = ('track', 'created_at', 'is_shared')
    search_fields = ('name', 'track__name')

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('user', 'track__name', 'phone_uuid', 'laptop_uuid', 'is_checked_in')
    list_filter = ('track', 'is_checked_in')
    search_fields = ('user__username', 'track__name')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'schedule', 'check_in_time', 'check_out_time', 'excuse', 'early_leave', 'late_check_in')
    list_filter = ('schedule', 'excuse', 'early_leave', 'late_check_in')
    search_fields = ('student__user__username', 'schedule__name')