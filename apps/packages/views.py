import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import SavedPackage
from .serializers import SavedPackageSerializer

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Saved Packages'],
    responses={200: SavedPackageSerializer(many=True)},
    description='List all saved package presets for the current user.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def package_list(request):
    packages = SavedPackage.objects.filter(user=request.user)
    serializer = SavedPackageSerializer(packages, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Packages'],
    request=SavedPackageSerializer,
    responses={201: SavedPackageSerializer},
    description='Create a new saved package preset.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def package_create(request):
    serializer = SavedPackageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user)

    logger.info(f"Saved package created: '{serializer.data['label']}' by {request.user.username}") # type: ignore
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['Saved Packages'],
    responses={200: SavedPackageSerializer},
    description='Get a specific saved package preset.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def package_detail(request, package_id):
    try:
        package = SavedPackage.objects.get(pk=package_id, user=request.user)
    except SavedPackage.DoesNotExist:
        return Response({'error': 'Package not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SavedPackageSerializer(package)
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Packages'],
    request=SavedPackageSerializer,
    responses={200: SavedPackageSerializer},
    description='Update a saved package preset.',
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def package_update(request, package_id):
    try:
        package = SavedPackage.objects.get(pk=package_id, user=request.user)
    except SavedPackage.DoesNotExist:
        return Response({'error': 'Package not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SavedPackageSerializer(package, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    logger.info(f"Saved package updated: '{package.label}' by {request.user.username}")
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Packages'],
    responses={204: None},
    description='Delete a saved package preset.',
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def package_delete(request, package_id):
    try:
        package = SavedPackage.objects.get(pk=package_id, user=request.user)
    except SavedPackage.DoesNotExist:
        return Response({'error': 'Package not found.'}, status=status.HTTP_404_NOT_FOUND)

    label = package.label
    package.delete()

    logger.info(f"Saved package deleted: '{label}' by {request.user.username}")
    return Response(status=status.HTTP_204_NO_CONTENT)