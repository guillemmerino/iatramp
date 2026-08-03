from django.urls import path

from .views import PlatformHomeView, PlatformSettingsView


urlpatterns = [
    path("", PlatformHomeView.as_view(), name="home"),
    path("configuracio/", PlatformSettingsView.as_view(), name="platform_settings"),
]

