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


class OnlyFieldsMixin:
    """Метод для модельки only_fields (поля для object_fields)
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
        result = []
        for field in cls._meta.fields:
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


class AbstractCacher:
    """Класс для кэширования записией модельки
       использовать для небольших таблиц (справочников)
       Использовать лучше в каком-нибудь файле,
       чтобы был постоянный экземпляр кэшера для модели
       например, form_cacher = AbstractCacher('data.Form')
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
    """Предварительное получение связанных моделей
       Выполнять после set_customer_for_model(model_instance=rows, customer=self.customer)
       Например,
       set_customer_for_model(model_instance=result, customer=self.customer)
       child_statement_model.prefetch_model_fk(rows=result, field_name='address')
       :param rows: Queryset
       :param field_name: поле, которое является ForeinKey
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
    cached_field_name = '%s_cached' % field_name
    cached_field_name_flag = '%s_flag' % cached_field_name
    field = cur_field[0]
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
