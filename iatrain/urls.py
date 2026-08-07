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
    path("organitzacions/", views.organization_list, name="iatrain_organization_list"),
    path("organitzacions/<slug:slug>/", views.organization_detail, name="iatrain_organization_detail"),
    path("gimnasos/", views.gym_list, name="iatrain_gym_list"),
    path("gimnasos/crear/", views.gym_create, name="iatrain_gym_create"),
    path("gimnasos/<int:pk>/", views.gym_detail, name="iatrain_gym_detail"),
    path("gimnasos/<int:pk>/editar/", views.gym_edit, name="iatrain_gym_edit"),
    path("gimnasos/<int:pk>/material/afegir/", views.gym_equipment_create, name="iatrain_gym_equipment_create"),
    path("gimnasos/<int:pk>/material/<int:equipment_pk>/editar/", views.gym_equipment_edit, name="iatrain_gym_equipment_edit"),
    path("engine/comencar/", views.training_start, name="iatrain_training_start"),
    path("engine/context-options/", views.context_options, name="iatrain_engine_context_options"),
]
