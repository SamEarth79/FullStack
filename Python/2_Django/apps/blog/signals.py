# apps/blog/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Post

@receiver(pre_save, sender=Post)
def set_published_at(sender, instance, **kwargs):
    if instance.status == Post.StatusOptions.PUBLISHED and instance.published_at is None:
        instance.published_at = timezone.now()