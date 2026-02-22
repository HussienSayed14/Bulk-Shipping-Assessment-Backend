import logging
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import SavedAddress
from .serializers import SavedAddressSerializer

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Saved Addresses'],
    responses={200: SavedAddressSerializer(many=True)},
    description='List all saved addresses for the current user.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def address_list(request):
    addresses = SavedAddress.objects.filter(user=request.user)
    serializer = SavedAddressSerializer(addresses, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Addresses'],
    request=SavedAddressSerializer,
    responses={201: SavedAddressSerializer},
    description='Create a new saved address.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def address_create(request):
    serializer = SavedAddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(user=request.user)

    logger.info(f"Saved address created: '{serializer.data['label']}' by {request.user.username}") # type: ignore
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['Saved Addresses'],
    responses={200: SavedAddressSerializer},
    description='Get a specific saved address.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def address_detail(request, address_id):
    try:
        address = SavedAddress.objects.get(pk=address_id, user=request.user)
    except SavedAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SavedAddressSerializer(address)
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Addresses'],
    request=SavedAddressSerializer,
    responses={200: SavedAddressSerializer},
    description='Update a saved address.',
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def address_update(request, address_id):
    try:
        address = SavedAddress.objects.get(pk=address_id, user=request.user)
    except SavedAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = SavedAddressSerializer(address, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    logger.info(f"Saved address updated: '{address.label}' by {request.user.username}")
    return Response(serializer.data)


@extend_schema(
    tags=['Saved Addresses'],
    responses={204: None},
    description='Delete a saved address.',
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def address_delete(request, address_id):
    try:
        address = SavedAddress.objects.get(pk=address_id, user=request.user)
    except SavedAddress.DoesNotExist:
        return Response({'error': 'Address not found.'}, status=status.HTTP_404_NOT_FOUND)

    label = address.label
    address.delete()

    logger.info(f"Saved address deleted: '{label}' by {request.user.username}")
    return Response(status=status.HTTP_204_NO_CONTENT)