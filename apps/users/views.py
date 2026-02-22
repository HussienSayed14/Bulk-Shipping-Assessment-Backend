import logging
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from .serializers import LoginSerializer, LoginResponseSerializer, UserSerializer
from .models import UserProfile

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Auth'],
    request=LoginSerializer,
    responses={200: LoginResponseSerializer},
    description='Login with username and password. Returns JWT tokens and user info.',
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data['username'] # type: ignore
    password = serializer.validated_data['password'] # type: ignore

    user = authenticate(username=username, password=password)

    if user is None:
        logger.warning(f"Failed login attempt for username: {username}")
        return Response(
            {'error': 'Invalid username or password.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        logger.warning(f"Login attempt for inactive user: {username}")
        return Response(
            {'error': 'This account is inactive.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Ensure user has a profile
    UserProfile.objects.get_or_create(user=user)

    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)

    logger.info(f"User logged in: {username}")

    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(user).data,
    })


@extend_schema(
    tags=['Auth'],
    responses={200: UserSerializer},
    description='Get the currently authenticated user profile and balance.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    # Ensure user has a profile
    UserProfile.objects.get_or_create(user=request.user)
    serializer = UserSerializer(request.user)
    return Response(serializer.data)