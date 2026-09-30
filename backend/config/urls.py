from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('community/admin/', admin.site.urls),
    path('community/api/', include('submissions.urls')),
]
admin.site.site_header = 'HITsz 日语社 · 内容审核'
admin.site.site_title = '日语社审核后台'
admin.site.index_title = '留言、歌曲投稿与通知'
admin.site.site_url = '/feedback/'

# The public site is served by Nginx in production. This is only a local preview.
import os
from django.conf import settings
if os.environ.get('JLA_LOCAL_SITE') and not settings.PRODUCTION:
    from django.urls import re_path
    from . import local_preview
    urlpatterns += [
        path('community/static/<path:path>', local_preview.admin_static),
        re_path(r'^(?P<path>.*)$', local_preview.site),
    ]
