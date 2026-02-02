from django.contrib import admin
from apps.common.models_abstract import AbstractDateTimeModel, AbstractShortDateTimeModel


class AbstractDateTimeModelAdmin(admin.ModelAdmin):
    """Модель для вывода полей created_at, update_at, deleted_at
    """
    def get_readonly_fields(self, request, obj=None):
        """Поля доступные только для чтения"""
        readonly = super().get_readonly_fields(request, obj)
        date_time_fields = ['created_at', 'updated_at'] if (
            AbstractShortDateTimeModel in self.model.__mro__ or AbstractDateTimeModel in self.model.__mro__
        ) else []
        # Дату удаления можно редактировать
        #date_time_fields = ['created_at', 'updated_at', 'deleted_at'] if AbstractDateTimeModel in self.model.__mro__ else []
        readonly_fields = [item for item in readonly] + date_time_fields
        return readonly_fields

    def get_list_display(self, request):
        list_display = [item for item in super().get_list_display(request)]
        if not hasattr(self, 'model'):
            return list_display
        model = getattr(self, 'model')
        if hasattr(model(), 'created_at') and not 'created_at' in list_display:
            list_display.append('created_at')
        if hasattr(model(), 'updated_at') and not 'updated_at' in list_display:
            list_display.append('updated_at')
        if hasattr(model(), 'deleted_at') and not 'deleted_at' in list_display:
            list_display.append('deleted_at')
        return list_display


class InputFilter(admin.SimpleListFilter):
    """Фильтр для ввода
       TODO: поправить counts (показать количество)
    """
    template = 'admin/input_filter.html'

    def lookups(self, request, model_admin):
        # Dummy, required to show the filter.
        return ((),)

    def choices(self, changelist):
        # Grab only the "all" option
        all_choice = next(super().choices(changelist))
        all_choice['query_parts'] = (
            (k, v)
            #for k, v in changelist.get_filters_params().items()
            # django 5 compatible
            for k, values in changelist.get_filters_params().items()
            for v in values
            # end djagno 5 compatible
            if k != self.parameter_name
        )
        yield all_choice
