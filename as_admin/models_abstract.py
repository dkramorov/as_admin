import json
import logging
import time

from django.apps import apps
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


class OnlyFieldsMixin:
    """Метод для модельки only_fields (поля для object_fields)
       Для того, чтобы поля не выводились в cls добавляем метод,
       который будет пропускать поля
       @classmethod
       def pass_fields(cls):
           return ('created_at', 'updated_at')
    """
    @classmethod
    def only_fields(cls) -> list:
        """Поля для маршрутов
        """
        only_types = (
            'BigAutoField', 'AutoField',
            'CharField', 'IntegerField', 'BigIntegerField', 'DecimalField',
            'DateField', 'DateTimeField',
            'BooleanField',
        )
        pass_fields = ()
        if hasattr(cls, 'pass_fields'):
            pass_fields = cls.pass_fields()
        result = []
        for field in cls._meta.fields:
            if field.name in pass_fields:
                continue
            if field.get_internal_type() in only_types:
                result.append(field.name)
        return result


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


def fetched_foreign_key(row, field_name: str):
    """Проверяем, вытащено ли поле из базы по Foreign key
       :param row: экземпляр модели
       :param field_name: поле модели (row) которое является fk
    """
    return row._state.fields_cache.get(field_name)


def object_fields(row,
                  pass_fields: tuple = None,
                  only_fields: tuple = None,
                  fk_only_keys: dict = None,
                  related_fields: list = None,
                  include_methods: list = None):
    """Все параметры объекта словарем (id, state, created...)
       :param pass_fields: ('пропускаем', 'эти', 'поля')
       :param only_fields: ('достаем', 'только', 'эти', 'поля')
       :param fk_only_keys: {'fk_field': ('достаем', 'только', 'эти', 'поля'), ...}
       :param related_fields: поля ссылающиеся на этот объект (OneToOneRel)
       :param include_methods: какие методы надо использовать как поля (метод модели в поле)
       Можно сделать row.full_clean(), что приведет
       все данные к нужному типу/виду"""
    if not row:
        return {}

    result = {}

    if not pass_fields:
        pass_fields = ()
    if not only_fields:
        only_fields = ()
    if not fk_only_keys:
        fk_only_keys = {}
    if not related_fields:
        related_fields = ()
    if not include_methods:
        include_methods = ()

    # OneToOneRel отношения (если у нас есть поле OneToOneField и мы запрашиваем его из связанной модели)
    if related_fields:
        for field in row.__class__._meta.related_objects:
            if field.name in related_fields and isinstance(field, models.fields.related.OneToOneRel):
                # Если связанный объект вытащен - заполняем его
                fetched_fk = fetched_foreign_key(row, field.name)
                if fetched_fk:
                    value = object_fields(fetched_fk,
                        only_fields=fk_only_keys.get(field.name),
                        fk_only_keys=fk_only_keys,
                    )
                    result[field.name] = value

    for field in row.__class__._meta.fields:
        if field.name in pass_fields:
            continue
        elif field.name in fk_only_keys:
            # Не пропускаем поля, если они указаны явно как foreign_keys
            pass
        elif only_fields and field.name not in only_fields:
            continue

        # TODO: ManyToManyField...
        if isinstance(field, (models.fields.related.ForeignKey, models.fields.related.OneToOneField)):
            value = getattr(row, '%s_id' % field.name)
            # Если связанный объект вытащен - заполняем его
            fetched_fk = fetched_foreign_key(row, field.name)
            if fetched_fk:
                value = object_fields(fetched_fk,
                    only_fields=fk_only_keys.get(field.name),
                    fk_only_keys=fk_only_keys,
                )
        else:
            value = getattr(row, field.name)

        if isinstance(field, (models.fields.IntegerField, models.fields.BigIntegerField)):
            if value != None:
                value = int(value)
        elif isinstance(field, models.fields.DateTimeField):
            if value:
                value = value.strftime('%Y-%m-%dT%H:%M:%S')
        elif isinstance(field, models.fields.DateField):
            if value:
                value = value.strftime('%Y-%m-%d')
        elif isinstance(field, models.fields.DecimalField):
            if value:
                value = float(value)
        elif isinstance(field, models.fields.BooleanField):
            if value:
                value = True
            else:
                value = False
        result[field.name] = value
    for include_method in include_methods:
        if hasattr(row, include_method):
            result[include_method] = getattr(row, include_method)
    return result


class AbstractCacher:
    """Класс для кэширования записией модельки
       использовать для небольших таблиц (справочников)
       Использовать лучше в каком-нибудь файле,
       чтобы был постоянный экземпляр кэшера для модели
       например, form_cacher = AbstractCacher('data.Form', ttl=60*3)
    """
    updated = None
    ttl = 60*60*6
    model = None
    objs = {}
    debug = False
    instance = None
    # Для кэширования ссылки на s3
    s3_fields = None

    def __init__(self,
                 instance: str = 'shop.PaymentMethod',
                 ttl: int = 60*60*6,
                 s3_fields: list = None):
        """Инициализация
           :param instance: метка модельки
           :param ttl: время жизни кэшированных записей
           :param s3_fields: поля с s3 полем
        """
        self.instance = instance
        self.ttl = ttl
        self.s3_fields = s3_fields
        self.objs = {}
        self.updated = None
        self.model = None

    def load_model(self):
        """Загрузить модель
        """
        if not self.model:
            self.model = apps.get_model(self.instance)

    def get_all(self):
        """Вытащить из базы все записи
        """
        now = time.time()
        if not self.updated or self.updated < now - self.ttl:
            self.update_all()
        else:
            if self.debug:
                logger.info('from cache %s' % self.model.__name__)
        return self.objs

    def update_all(self):
        """Обновить информацию
        """
        self.load_model()
        if self.debug:
            logger.info('updating cache %s' % self.model.__name__)
        self.updated = time.time()
        query = self.model.objects.all()
        for item in query:
            self.objs[item.id] = object_fields(item)
            if self.s3_fields:
                for s3_field in self.s3_fields:
                    if hasattr(item, s3_field) and getattr(item, s3_field):
                        if item._meta.get_field(s3_field).get_internal_type() == 'FileField':
                            self.objs[item.id]['%s_FileField' % s3_field] = getattr(item, s3_field).url

    def get_by_pk(self,
                  pk: int,
                  only_fields: list = None,
                  pass_fields: list = None,
                  only_fields_from_model: bool = False):
        """Получение по ид записи из кэша
           Модель при первом вызове еще не задана и будет вычислена из instance
           only_fields можно вытащить по staticmethod после этого
           :param pk: идентификатор
           :param only_fields: в результат записывать только поля из этого списка
           :param pass_fields: в результат не записывать поля из этого списка
           :param only_fields_from_model: если в моделе есть only_fields то использовать его
        """
        try:
            pk = int(pk)
        except Exception:
            pk = 0
        items = self.get_all()
        result = items.get(pk, {})
        if not pass_fields:
            pass_fields = []
        if only_fields_from_model and not only_fields and hasattr(self.model, 'only_fields'):
            # Если в классе есть метод only_fields, используем
            only_fields = getattr(self.model, 'only_fields')()
        if only_fields:
            return {k: v for k, v in result.items() if k in only_fields and k not in pass_fields}
        return {k: v for k, v in result.items() if k not in pass_fields}


def set_customer_for_model(model_instance, customer):
    """Задать для модели ид пользователя, который выполняет маршрут,
       модель получена в маршруте self.retrieve(str(item.id).strip(), is_force=True),
       если хотим ограничить видимость каких-то сущностей,
       в методах будем проверять hasattr(model_instance, customer_from_route_key)
       :param model_instance: экземпляр модели
       :param customer: пользователь
    """
    if not model_instance or not customer:
        return
    if not isinstance(model_instance, (list, tuple, models.QuerySet)):
        # Если передается моделька вместо списка
        model_instance = [model_instance]
    for item in model_instance:
        setattr(item, customer_from_route_key, customer)


def prefetch_model_fk(rows: list, field_name: str):
    """Предварительное получение связанных моделей по ForeignKey
       Выполнять после set_customer_for_model(model_instance=rows, customer=self.customer)
       Например,
       set_customer_for_model(model_instance=result, customer=self.customer)
       child_statement_model.prefetch_model_fk(rows=result, field_name='address')
       :param rows: Queryset
       :param field_name: поле, которое является ForeignKey
    """
    if not rows:
        return
    customer_from_route = None
    if not isinstance(rows, (list, tuple, models.QuerySet)):
        # Если передается моделька вместо списка
        rows = [rows]
    if rows:
        if hasattr(rows[0], customer_from_route_key):
            customer_from_route = getattr(rows[0], customer_from_route_key)
    if not customer_from_route:
        logger.info('[WARNING]: execute prefetch_model_fk %s_id, customer_from_route_key not set' % (
            field_name,
        ))
        #return
    model = rows[0]._meta.model
    cur_field = [field for field in model._meta.fields if field.name == field_name]
    if not cur_field:
        logger.info('can not execute prefetch_model_fk %s.%s_id, because cur_field not found' % (
            model._meta.label,
            field_name,
        ))
        return
    field = cur_field[0]
    cached_field_name = '%s_cached' % field_name
    cached_field_name_flag = '%s_flag' % cached_field_name
    rel_model = field.related_model
    fname = '%s_id' % field.name
    ids = {
        getattr(row, fname): None for row in rows if not hasattr(row, cached_field_name_flag)
    }
    if not ids:
        return

    objs = rel_model.objects.filter(pk__in=ids.keys())
    for obj in objs:
        ids[obj.id] = obj

    # Пробрасываем пользователя всем вытащенным объектам
    set_customer_for_model(customer=customer_from_route, model_instance=objs)
    for row in rows:
        rel_pk = getattr(row, fname)
        obj = ids.get(rel_pk)
        setattr(row, cached_field_name, obj)
        setattr(row, cached_field_name_flag, '1')

def prefetch_model_related(rows: list, related_name: str, select_related: list = None):
    """Предварительное получение связанных моделей по ForeignKey реверсивно,
       то есть, находим row.related_name_set.all()
       например, principal.principaltype_set.field это PrincipalType.ForeignKey поле на Principal
       Выполнять после set_customer_for_model(model_instance=rows, customer=self.customer)
       Например,
       set_customer_for_model(model_instance=result, customer=self.customer)
       child_statement_model.prefetch_model_related(rows=result, field_name='files_set')
       :param rows: Queryset
       :param related_name: поле, которое указано в другой модели как ForeignKey
       :param select_related: список полей, которые надо сразу доставать
    """
    if not rows:
        return
    customer_from_route = None
    if not isinstance(rows, (list, tuple, models.QuerySet)):
        # Если передается моделька вместо списка
        rows = [rows]
    if rows:
        if hasattr(rows[0], customer_from_route_key):
            customer_from_route = getattr(rows[0], customer_from_route_key)
    if not customer_from_route:
        logger.info('[WARNING]: execute prefetch_model_related %s, customer_from_route_key not set' % (
            related_name,
        ))
        #return
    if not hasattr(rows[0], related_name):
        logger.info('[ERROR]: execute prefetch_model_related failed, because field %s absent in model %s' % (
            related_name,
            rows[0]._meta.model,
        ))
        return
    related_manager = getattr(rows[0], related_name)
    related_model = related_manager.model
    related_field = related_manager.field

    cached_related_name = '%s_cached' % related_name
    cached_related_name_flag = '%s_flag' % cached_related_name

    ids = {}
    for row in rows:
        if hasattr(row, cached_related_name_flag):
            continue
        setattr(row, cached_related_name, [])
        ids[row.id] = row

    if not ids:
        return

    cond = {'%s__in' % related_field.name: ids.keys()}
    if not select_related:
        select_related = []
    objs = related_model.objects.select_related(*select_related).filter(**cond)
    for obj in objs:
        field_name = '%s_id' % related_field.name
        field_value = getattr(obj, field_name)
        row = ids.get(field_value)
        if row:
            cached_related = getattr(row, cached_related_name)
            cached_related.append(obj)
            setattr(row, cached_related_name_flag, '1')

    # Пробрасываем пользователя всем вытащенным объектам
    set_customer_for_model(customer=customer_from_route, model_instance=objs)
