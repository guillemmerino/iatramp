from django.urls import path

from .views import IatrainHomeView


urlpatterns = [
    path("", IatrainHomeView.as_view(), name="iatrain_home"),
]

