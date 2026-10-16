from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("events/", views.EventSearchView.as_view()),
    path("uploads/", views.ArchiveUploadView.as_view()),
    path("ingestions/", views.IngestionListView.as_view()),
    path("ingestions/<int:pk>/", views.IngestionDetailView.as_view()),
    path("summary/", views.SummaryView.as_view()),
]
