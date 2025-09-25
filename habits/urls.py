from django.urls import path, include 
from rest_framework.routers import DefaultRouter
from .views import HabitViewSet, HabitRecordViewSet

router = DefaultRouter()

router.register('habits', HabitViewSet, "habit")
router.register('habit-record', HabitRecordViewSet, "habitrecord")

urlpatterns = router.urls

