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
    from django.conf import settings
    from django.urls import path, include, re_path
    from django.views.static import serve
    ...
    path('admin/', include('as_admin.urls')),
    ...


