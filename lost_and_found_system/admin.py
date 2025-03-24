from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import LostItem, FoundItem, MatchedItem, ItemStatusChoices

# Register your models here.
admin.site.register(LostItem)
admin.site.register(FoundItem)
admin.site.register(MatchedItem)
