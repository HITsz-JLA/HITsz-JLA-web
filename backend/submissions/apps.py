from django.apps import AppConfig
from django.db.backends.signals import connection_created


def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite' and 'memory' not in str(connection.settings_dict['NAME']):
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode=WAL;')


class SubmissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'submissions'
    verbose_name = '社团互动'

    def ready(self):
        connection_created.connect(configure_sqlite, dispatch_uid='community_sqlite_wal')
