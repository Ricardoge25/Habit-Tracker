from django.urls import path, include 
from rest_framework.routers import DefaultRouter
from .views import HabitViewSet, HabitRecordViewSet, RegisterViewSet, CategoryViewSet, ProgressViewSet

router = DefaultRouter()

router.register('habits', HabitViewSet, "habit")
router.register('habit-record', HabitRecordViewSet, "habitrecord")
router.register('users', RegisterViewSet, "register")
router.register('categories', CategoryViewSet, "category")
router.register('progress', ProgressViewSet, "progress")

urlpatterns = router.urls

