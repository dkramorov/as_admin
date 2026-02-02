from django.urls import reverse


def format_item_display(cls, item):
    """Форматирование для ModelLookup(LookupChannel)
       в form = make_ajax_form(...)
       Класс должен иметь метод get_name
       :param cls: класс (надо передавать self из Lookup)
       :param item: экземпляр модели
    """
    edit_model_link = 'admin:%s_%s_change' % (
        cls.model._meta.model._meta.app_label,
        cls.model._meta.model.__name__.lower(),
    )
    edit_url = reverse(edit_model_link, args=(item.id, ))
    return """
<span>%s</span> 
<a id='change_id_role_{}'
   class='related-widget-wrapper-link change-related' 
   href='%s' target='_blank'>
  <img src="/static/admin/img/icon-changelink.svg" alt="Change">
</a>"""  % (item.get_name(), edit_url)