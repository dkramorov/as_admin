from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, re_path


# TODO: ModelHelper переписать здесь
class AsAdminAbstract(models.Model):
    """Модель для панели управления,
       добавляет маршруты по умолчанию для табличного представления и редактирования модели
    """
    class Meta:
        abstract = True

    @classmethod
    def get_mh_vars(cls):
        """Получение переменных для views
        """
        app_label = cls._meta.app_label.lower()
        model_name = cls._meta.model_name.lower()
        mh_vars = {
            'menu': app_label,
            'submenu': model_name,
            'cur_app': app_label,
            'singular_obj': cls._meta.verbose_name,
            'plural_obj': cls._meta.verbose_name_plural,
            'rp_singular_obj': cls._meta.verbose_name, #'пользователя',
            'rp_plural_obj': cls._meta.verbose_name_plural, #'пользователей',
            'template_prefix': '%s_%s_' % (app_label, model_name),
            'action_create': 'Создание',
            'action_edit': 'Редактирование',
            'action_drop': 'Удаление',
            'show_urla': 'show_%s' % model_name,
            'create_urla': 'create_%s' % model_name,
            'edit_urla': 'edit_%s' % model_name,
            'model': cls,
        }
        if hasattr(cls, 'get_vars'):
            get_vars = getattr(cls, 'get_vars')
            if callable(get_vars):
                mh_vars.update(get_vars())
        return mh_vars

    @classmethod
    def get_urls(cls,
                 with_show_url: bool = True,
                 with_edit_url: bool = True,
                 with_search_url: bool = True):
        """Машруты для таблицы и редактирования модели
           надо наследоваться от этой модели, затем
           urls.py: urlpatterns += models.<MODELNAME>.get_urls()
           :param with_show_url: список
           :param with_edit_url: редактирование
           :param with_search_url: поиск
        """
        urlpatterns = []
        app_label = cls._meta.app_label.lower()
        model_name = cls._meta.model_name.lower()
        if with_show_url:
            urlpatterns.append(
                path('admin/%s/' % model_name,
                     cls.get_show_url(),
                     name='show_%s' % model_name)
            )
        if with_edit_url:
            urlpatterns += [
                re_path('^admin/%s/(?P<action>create)/$' % model_name,
                        cls.get_edit_url(form_class=form_class),
                        name='create_%s' % model_name),
                re_path('^admin/%s/(?P<action>edit|drop|img)/(?P<row_id>[0-9]{1,11})/$' % model_name,
                        cls.get_edit_url(form_class=form_class),
                        name='edit_%s' % model_name),
            ]
        if with_search_url:
            urlpatterns.append(
                path('%s/search/' % model_name,
                     cls.get_search_url(form_class=form_class),
                     name='search_%s' % model_name),
            )
        return urlpatterns


    @classmethod
    def get_show_url(cls):
        """Получение view для показа таблицы
        """
        @login_required
        def show_view(request, *args, **kwargs):
            """Вывод таблицы записей
               :param request: HttpRequest
            """
            app_label = cls._meta.app_label.lower()
            model_name = cls._meta.model_name.lower()
            mh_vars = cls.get_mh_vars()
            #mh = create_model_helper(mh_vars=mh_vars, request=request)

            context = {k: v for k, v in mh_vars.items() if isinstance(v, str)}
            # Вся выборка только через аякс
            if request.is_ajax():
                result = []
                #rows = mh.standard_show()
                #for row in rows:
                #    result.append(object_fields(row))
                #if request.GET.get('page'):
                #    result = {
                #        'data': result,
                #        'last_page': mh.raw_paginator['total_pages'],
                #        'total_records': mh.raw_paginator['total_records'],
                #        'cur_page': mh.raw_paginator['cur_page'],
                #        'by': mh.raw_paginator['by'],
                #    }
                return JsonResponse(result, safe=False)

            template = '%stable.html' % (mh_vars['template_prefix'])
            return render(request, template, context)
        return show_view


    # TODO:
    @classmethod
    def get_edit_url(cls, form_class=None):
        """Получение view для редактирования (создания и удаления) записи
           :param form_class: класс формы с настройками, которые нужны ModelFormConstructor
        """
        from apps.former.model_fc import ModelFormConstructor

        app_label = cls._meta.app_label.lower()
        model_name = cls._meta.model_name.lower()

        @login_required
        def edit_view(request, action: str, row_id: int = None, *args, **kwargs):
            """Создание/редактирование записи
               :param request: HttpRequest
               :param action: действие над объектом (создание/редактирование/удаление)
               :param row_id: ид записи
            """
            mh_vars = cls.get_mh_vars()
            mh = create_model_helper(mh_vars=mh_vars, request=request, action=action)
            row = mh.get_row(row_id)
            context = mh.context
            template = '%sedit.html' % (mh.template_prefix, )

            if mh.error:
                return redirect('%s?error=not_found' % (mh.root_url, ))
            if request.method == 'GET':
                if action == 'create':
                    mh.breadcrumbs_add({
                        'link': mh.url_create,
                        'name': '%s %s' % (mh.action_create, mh.rp_singular_obj),
                    })
                elif action == 'edit' and row:
                    mh.breadcrumbs_add({
                        'link': mh.url_edit,
                        'name': '%s %s' % (mh.action_edit, mh.rp_singular_obj),
                    })
                elif action == 'drop' and row:
                    if mh.permissions['drop']:
                        row.delete()
                        mh.row = None
                        context['success'] = '%s удален' % (mh.singular_obj, )
                    else:
                        context['error'] = 'Недостаточно прав'
            elif request.method == 'POST':
                pass_fields = ()
                mh.post_vars(pass_fields=pass_fields)
                if action == 'create' or (action == 'edit' and row):
                    if action == 'create':
                        if mh.permissions['create']:
                            mh.row = mh.model()
                            mh.save_row()
                            context['success'] = 'Данные успешно записаны'
                        else:
                            context['error'] = 'Недостаточно прав'
                    if action == 'edit':
                        if mh.permissions['edit']:
                            mh.save_row()
                            context['success'] = 'Данные успешно записаны'
                        else:
                            context['error'] = 'Недостаточно прав'
                elif action == 'img' and request.FILES:
                    mh.uploads()
            if mh.row:
                context['row'] = object_fields(mh.row)
                context['row']['folder'] = mh.row.get_folder()
                context['redirect'] = mh.get_url_edit()
            if request.is_ajax() or action == 'img':
                return JsonResponse(context, safe=False)

            # Конструктор форм
            model_form_constructor = ModelFormConstructor(
                model_helper=mh,
                #title=mh_vars['singular_obj'],
                #only_fields=model_only_fields, # TODO
                form_class=form_class,
            )
            context['model_form_constructor'] = model_form_constructor

            return render(request, template, context)
        return edit_view

    @classmethod
    def get_search_url(cls, form_class=None):
        """Получение view для поиска записей
           :param form_class: класс формы с настройками, которые нужны ModelFormConstructor
        """
        from apps.former.model_fc import ModelFormConstructor

        app_label = cls._meta.app_label.lower()
        model_name = cls._meta.model_name.lower()

        def search_view(request, *args, **kwargs):
            """Поиск записей"""
            result = {'results': []}

            mh_vars = cls.get_mh_vars()
            mh = create_model_helper(mh_vars=mh_vars, request=request, action='search')
            # Поля для поиска
            mh.search_fields = mh_vars.get('search_fields') or ['id']
            # Поля для фильтра
            for item in mh_vars.get('list_filters', []):
                if request.GET.get(item):
                    mh.filter_add({item: request.GET[item]})

            rows = mh.standard_show()
            for row in rows:
                name = row.get_name()
                result['results'].append({'text': name, 'id': row.id})

            if mh.raw_paginator['cur_page'] == mh.raw_paginator['total_pages']:
                result['pagination'] = {'more': False}
            else:
                result['pagination'] = {'more': True}
            return JsonResponse(result, safe=False)
        return search_view
