from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="iatrain_home"),
    path("perfils/actualitzar/", views.update_profile, name="iatrain_profile_update"),
    path("perspectiva/", views.select_perspective, name="iatrain_perspective"),
    path("gimnastes/", views.athlete_list, name="iatrain_athlete_list"),
    path("gimnastes/afegir/", views.athlete_create, name="iatrain_athlete_create"),
    path("gimnastes/<int:pk>/", views.athlete_detail, name="iatrain_athlete_detail"),
    path("grups/", views.group_list, name="iatrain_group_list"),
    path("grups/crear/", views.group_create, name="iatrain_group_create"),
    path("grups/<int:pk>/", views.group_detail, name="iatrain_group_detail"),
    path("grups/<int:pk>/membres/<int:membership_pk>/retirar/", views.group_member_remove, name="iatrain_group_member_remove"),
]
