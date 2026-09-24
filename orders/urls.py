from django.urls import path
from . import views

app_name = "orders"
urlpatterns = [
    path("", views.order_list, name="list"),
    path("new/", views.editor, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.editor, name="edit"),
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
    path("files/<int:pk>/download/", views.download, name="download"),
]
