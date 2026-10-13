from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate


def grant_visit_permission(sender, **kwargs):
    if sender.name != 'submissions':
        return
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType
    from .models import PageVisit
    group = Group.objects.filter(name='社团内容审核员').first()
    if group:
        permission, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(PageVisit),
            codename='view_pagevisit', defaults={'name': 'Can view 页面访问记录'})
        group.permissions.add(permission)


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
        post_migrate.connect(grant_visit_permission, sender=self, dispatch_uid='community_visit_permission')
