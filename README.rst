Установка пакетом
-----------
Для локальной разработки::
    pip install -e packages/as_admin

Для создания пакета
https://docs.python.org/3.10/distutils/introduction.html#distutils-simple-example
https://docs.python.org/3.10/distutils/sourcedist.html
python setup.py sdist

1. Добавляем "as_admin" в settings.py секцию INSTALLED_APPS::
    INSTALLED_APPS = [
        ...,
        'as_admin',
    ]

2. Добавляем ссылки в urls.py::
    from django.urls import path, include
    ...
    path('admin/', include('as_admin.urls')),
    ...

3. Не забыть при наследовании от абстрактных моделей в приложениях создавать
apps.py::
  from django.apps import AppConfig
  class YourConfig(AppConfig):
      default_auto_field = 'django.db.models.BigAutoField'
      name = 'apps.your_app'
      verbose_name = 'Your app name'
