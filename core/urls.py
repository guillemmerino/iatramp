from django.urls import path

from .views import (
    PlatformHomeView,
    organization_create,
    organization_detail,
    organization_edit,
    organization_join,
    organization_member_access,
    organization_request_cancel,
    organization_request_review,
    organizations,
    platform_settings_redirect,
    profile,
)


urlpatterns = [
    path("", PlatformHomeView.as_view(), name="home"),
    path("configuracio/", platform_settings_redirect, name="platform_settings"),
    path("perfil/", profile, name="profile"),
    path("organitzacions/", organizations, name="organizations"),
    path("organitzacions/nova/", organization_create, name="organization_create"),
    path("organitzacions/sollicituds/<int:pk>/cancel-lar/", organization_request_cancel, name="organization_request_cancel"),
    path(
        "organitzacions/sollicituds/<int:pk>/<str:decision>/",
        organization_request_review,
        name="organization_request_review",
    ),
    path("organitzacions/<slug:slug>/", organization_detail, name="organization_detail"),
    path("organitzacions/<slug:slug>/editar/", organization_edit, name="organization_edit"),
    path("organitzacions/<slug:slug>/unir-se/", organization_join, name="organization_join"),
    path(
        "organitzacions/<slug:slug>/membres/<int:pk>/accessos/",
        organization_member_access,
        name="organization_member_access",
    ),
]
