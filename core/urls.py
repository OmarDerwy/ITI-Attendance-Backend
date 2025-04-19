"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.urls import path, include
from . import views
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from debug_toolbar.toolbar import debug_toolbar_urls
API_PREFIX = 'api/v1/'


urlpatterns = [
    path('admin/', admin.site.urls),
    # drf-spectacular
    path(f'{API_PREFIX}schema/', SpectacularAPIView.as_view(), name='schema'),
    path(f'{API_PREFIX}schema-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path(f'{API_PREFIX}schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # test endpoint
    path(f'{API_PREFIX}dummy/', views.hello_world, name='hello-world'),
    # apps
    path(f'{API_PREFIX}lost-and-found/', include('lost_and_found_system.urls')),
    path(f'{API_PREFIX}accounts/', include('users.urls')),
    path(f'{API_PREFIX}attendance/', include('attendance_management.urls')),
] + debug_toolbar_urls()
