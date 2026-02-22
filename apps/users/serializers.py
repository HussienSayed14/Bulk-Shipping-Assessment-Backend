from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['company_name', 'balance']
        read_only_fields = ['balance']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']
        read_only_fields = ['id', 'username', 'email']


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        help_text='Your username'
    )
    password = serializers.CharField(
        write_only=True,
        help_text='Your password'
    )


class LoginResponseSerializer(serializers.Serializer):
    """Serializer for Swagger documentation of login response."""
    access = serializers.CharField(help_text='JWT access token')
    refresh = serializers.CharField(help_text='JWT refresh token')
    user = UserSerializer()