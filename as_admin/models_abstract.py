import json
import logging
from django.db import models
from django.db import connections

from django.contrib.contenttypes.models import ContentType
from django.contrib.admin.models import LogEntry, ADDITION


logger = logging.getLogger()
customer_from_route_key = 'customer_from_route'


def raw_query(query, db: str = 'default', action: str = None):
    """Сырой запрос
    """
    action = query.split(' ')[0].lower()
    if not action:
        action = 'select'
    result = None
    with connections[db].cursor() as cursor:
        result = cursor.execute(query)
        if action == 'select':
            result = cursor.fetchall()
    return result



class AbstractLogModel(models.Model):
    class Meta:
        abstract = True

    def log_action(self,
                   message: str = '',
                   user_id: int = 1,
                   action_flag: int = ADDITION):
        """Логирование события
           :param message: сообщение
           :param user_id: от имени какого пользователя админки записать событие
           :param action_flag: флаг
        """
        LogEntry.objects.log_action(
            user_id=user_id,
            content_type_id=ContentType.objects.get_for_model(self).pk,
            object_id=self.pk,
            object_repr='%s' % self,
            action_flag=action_flag,
            change_message=message,
        )


class AbstractShortDateTimeModel(models.Model):
    """Модель с датой создания и обновления
    """
    created_at = models.DateTimeField(blank=True, null=True, db_index=True, auto_now_add=True,
        verbose_name='Дата создания')
    updated_at = models.DateTimeField(blank=True, null=True, db_index=True, auto_now=True,
        verbose_name='Дата обновления')

    class Meta:
        abstract = True


class AbstractDateTimeModel(AbstractShortDateTimeModel):
    """Default datetime columns
    """
    deleted_at = models.DateTimeField(blank=True, null=True, db_index=True,
        verbose_name='Дата удаления')

    class Meta:
        abstract = True


class WithJsonFieldsMixin:
    """Модель с json полями
    """
    def get_json_field(self, field_name: str) -> list:
        """Вспомогательная функция для получения json-поля
           Например, available_values = models.TextField(verbose_name='Возможные значения')
               def get_available_values(self):
                   # можно через or {}
                   return self.get_json_field(field_name='available_values') or []
           :param field_name: имя поля
        """
        field_value = getattr(self, field_name)
        if isinstance(field_value, str):
            try:
                field_value = json.loads(field_value.replace('\'', '"'))
            except Exception as e:
                logger.info('exception for json field %s is %s' % (field_name, e))
        return field_value or []


class AbstractNameModel(models.Model):
    """Default first_name, last_name, middle_name model
    """
    first_name = models.CharField(max_length=255, blank=True, null=True, db_index=True,
        verbose_name='Имя')
    last_name = models.CharField(max_length=255, blank=True, null=True, db_index=True,
        verbose_name='Фамилия')
    patronymic = models.CharField(max_length=255, blank=True, null=True, db_index=True,
        verbose_name='Отчество')

    class Meta:
        abstract = True

    def get_name(self):
        """Получение строкового представления модельки
        """
        return '#%s %s' % (self.id, ' '.join([
            self.last_name or '',
            self.first_name or '',
            self.patronymic or '',
        ]))


def set_customer_for_model(model_instance, customer):
    """Задать для модели ид пользователя, который выполняет маршрут,
       модель получена в маршруте self.retrieve(str(item.id).strip(), is_force=True),
       если хотим ограничить видимость каких-то сущностей,
       в методах будем проверять hasattr(model_instance, customer_from_route_key)
       :param model_instance: экземпляр модели
       :param customer: кто просматривает маршрут
    """
    if not model_instance or not customer:
        return
    #customer_id = customer if isinstance(customer, int) else customer.id
    if not isinstance(model_instance, (list, tuple, models.QuerySet)):
        # Если передается моделька вместо списка
        model_instance = [model_instance]
    for item in model_instance:
        #setattr(item, customer_from_route_key, customer_id)
        setattr(item, customer_from_route_key, customer)


def prefetch_model_fk(rows: list, field_name: str):
    """Предварительное получение связанных моделей
       Выполнять после set_customer_for_model(model_instance=rows, customer=self.customer)
       Например,
       set_customer_for_model(model_instance=result, customer=self.customer)
       child_statement_model.prefetch_model_fk(rows=result, field_name='address')
       :param rows: Queryset
       :param field_name: поле, которое является ForeinKey
    """
    customer_from_route = None
    if not isinstance(rows, (list, tuple, models.QuerySet)):
        # Если передается моделька вместо списка
        rows = [rows]
    if rows:
        if hasattr(rows[0], customer_from_route_key):
            customer_from_route = getattr(rows[0], customer_from_route_key)
    if not customer_from_route:
        logger.info('can not execute prefetch_model_fk %s_id, because customer_from_route_key not set' % (
            field_name,
        ))
        return
    model = rows[0]._meta.model
    cur_field = [field for field in model._meta.fields if field.name == field_name]
    if not cur_field:
        logger.info('can not execute prefetch_model_fk %s.%s_id, because cur_field not found' % (
            model._meta.label,
            field_name,
        ))
        return
    field = cur_field[0]
    rel_model = field.related_model
    fname = '%s_id' % field.name
    ids = {getattr(row, fname): None for row in rows}
    objs = rel_model.objects.filter(pk__in=ids.keys())
    for obj in objs:
        ids[obj.id] = obj
    for row in rows:
        rel_pk = getattr(row, fname)
        obj = ids.get(rel_pk)
        setattr(row, '%s_cached' % field_name, obj)
