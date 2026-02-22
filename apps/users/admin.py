from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Show UserProfile inline on the User admin page."""
    model = UserProfile
    can_delete = False
    verbose_name = 'Profile'
    verbose_name_plural = 'Profile'


# Unregister the default User admin and register our custom one
admin.site.unregister(User)



@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'date_joined']
    list_display_links = ['id', 'username']
    inlines = [UserProfileInline]


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'company_name', 'balance', 'created_at']
    search_fields = ['user__username', 'user__email', 'company_name']
    readonly_fields = ['created_at', 'updated_at']