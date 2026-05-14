from typing import Required
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Post, Tag, Comment
from django.contrib.auth import get_user_model

User = get_user_model()

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model=Tag
        fields = ['id', 'name', 'slug']

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model=User
        fields = ['id', 'email', 'username']

class PostCreateSerializer(serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)

    class Meta:
        model=Post
        fields=['title', 'slug', 'body', 'status', 'tags']
        
    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        post = Post.objects.create(**validated_data)
        post.tags.set(tags)
        return post

class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(read_only=True, many=True)
    
    class Meta:
        model=Post
        fields=['id', 'title', 'slug', 'author', 'status', 'tags', 'published_at', 'created_at']
        
class PostDetailSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(read_only=True, many=True)
    
    class Meta:
        model=Post
        fields=['id', 'title', 'slug', 'body', 'author', 'status', 'tags', 'published_at', 'created_at', 'updated_at']
        
class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    
    class Meta:
        model=Comment
        fields=['id', 'post', 'author', 'body', 'created_at']

class CommentCreateSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    
    class Meta:
        model=Comment
        fields=['id', 'post', 'author', 'body', 'created_at']

    def create(self, validated_data):
        return Comment.objects.create(**validated_data)

        
         
