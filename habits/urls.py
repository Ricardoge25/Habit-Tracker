from django.urls import path, include 
from rest_framework.routers import DefaultRouter
from .views import HabitViewSet, HabitRecordViewSet, RegisterViewSet, CategoryViewSet

router = DefaultRouter()

router.register('habits', HabitViewSet, "habit")
router.register('habit-record', HabitRecordViewSet, "habitrecord")
router.register('register', RegisterViewSet, "register")
router.register('categories', CategoryViewSet, "category")

urlpatterns = router.urls

