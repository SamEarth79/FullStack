from django.shortcuts import render
from rest_framework import viewsets
from .models import Post
from .permissions import IsAuthorOrReadOnly
from .serializers import PostCreateSerializer, PostSerializer, PostDetailSerializer

# Create your views here.
class PostViewSet(viewsets.ModelViewSet):
    permission_classes=[IsAuthorOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        if self.action in ['list', 'retrieve']:
            if user.is_authenticated:
                # Authors see their own drafts + all published
                from django.db.models import Q
                return Post.objects.filter(
                    Q(status=Post.Status.PUBLISHED) | Q(author=user)
                ).select_related('author').prefetch_related('tags', 'comments')
            # Anonymous users see published only
            return Post.objects.filter(
                status=Post.Status.PUBLISHED
            ).select_related('author').prefetch_related('tags', 'comments')
        # For create/update/delete — no status filter
        return Post.objects.select_related('author').prefetch_related('tags', 'comments')

    def get_serializer_class(self):
        if self.action in ['list']:
            return PostSerializer
        elif self.action in ['retrieve']:
            return PostDetailSerializer
        else:
            return PostCreateSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    