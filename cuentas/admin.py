from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    #esto solo es para el desarrollo

    fieldsets = UserAdmin.fieldsets + (
        ("Seguridad", {"fields": ("debe_cambiar_password",)}),
    )
    list_display = ("username", "first_name", "last_name", "is_active", "last_login")
