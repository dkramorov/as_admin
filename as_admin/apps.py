from django.apps import AppConfig


class AsAdminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'as_admin'
    verbose_name = 'Панель управления'
