"""
URL configuration for padosiagent project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="Padosi Agent API",
      default_version='v1',
      description="API documentation for Padosi Agent",
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

from apps.agents.views.dashboard import serve_private_file

urlpatterns = [
    re_path(r'^api/docs(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('media/app/private/<path:file_path>', serve_private_file, name='serve_private_file'),
    path('django-admin/', admin.site.urls),
    path('', include('apps.admin_panel.urls')),
    path('', include('apps.agents.urls')),
    path('chatbot/', include('chatbot.urls', namespace='chatbot')),
    path('', include('apps.home.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

