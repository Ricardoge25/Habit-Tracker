from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User 
from .models import Progress

@receiver(post_save, sender=User)
def create_user_progress(sender, instance, created, **kwargs):
  if created:
    Progress.objects.create(user=instance, level=1, experience=0)