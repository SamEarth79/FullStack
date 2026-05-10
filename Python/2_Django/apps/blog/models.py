from django.db import models
from django.conf import settings

# Create your models here.
class Post(models.Model):
    class StatusOptions(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    title = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, max_length=50)
    body = models.TextField()
    author = models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    status = models.CharField(max_length=10, choices=StatusOptions.choices, default=StatusOptions.DRAFT)
    tags = models.ManyToManyField(to='Tag', blank=True, related_name='posts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Post'
        verbose_name_plural = 'Posts'

    def __str__(self):
        return self.title

class Comment(models.Model):
    post = models.ForeignKey(to=Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    body = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comment'
        verbose_name_plural = 'Comments'

    def __str__(self):
        return self.body[:20]

class Tag(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, max_length=50)

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

    def __str__(self):
        return self.name



