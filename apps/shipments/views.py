import logging
from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from apps.shipments.services.address_verifier import verify_record_address

from .models import ShipmentBatch, ShipmentRecord
from .serializers import (
    ShipmentBatchSerializer,
    ShipmentBatchListSerializer,
    ShipmentRecordSerializer,
    ShipmentRecordUpdateSerializer,
    CSVUploadSerializer,
    BulkUpdateFromAddressSerializer,
    BulkUpdatePackageSerializer,
    BulkUpdateShippingSerializer,
    BulkDeleteSerializer,
    PurchaseSerializer,
    PurchaseResponseSerializer,
)
from .services.csv_parser import parse_csv
from .services.validator import validate_and_update_record, validate_records_bulk
from .services.rate_calculator import (
    calculate_cost_for_record,
    get_cheapest_service,
    get_available_services,
)
from apps.addresses.models import SavedAddress
from apps.packages.models import SavedPackage
from apps.users.models import UserProfile
from apps.billing.models import Transaction

logger = logging.getLogger(__name__)


# =============================================================================
# CSV UPLOAD
# =============================================================================

@extend_schema(
    tags=['Batches'],
    request=CSVUploadSerializer,
    responses={201: ShipmentBatchSerializer},
    description='Upload a CSV file to create a new shipment batch. Parses the file, validates records, and returns batch details.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_csv(request):
    serializer = CSVUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    file = serializer.validated_data['file']# type: ignore
    logger.info(f"User {request.user.username} uploading CSV: {file.name}")

    # Parse CSV
    result = parse_csv(file)

    if result['errors'] and not result['records']:
        return Response(
            {'error': 'Failed to parse CSV file.', 'details': result['errors']},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not result['records']:
        return Response(
            {'error': 'No data rows found in the CSV file.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Create batch and records in a transaction
    with transaction.atomic():
        batch = ShipmentBatch.objects.create(
            user=request.user,
            file_name=file.name,
            status=ShipmentBatch.Status.DRAFT,
        )

        records = []
        for record_data in result['records']:
            record = ShipmentRecord(
                batch=batch,
                row_number=record_data.pop('row_number'),
                from_first_name=record_data.get('from_first_name', ''),
                from_last_name=record_data.get('from_last_name', ''),
                from_address1=record_data.get('from_address1', ''),
                from_address2=record_data.get('from_address2', ''),
                from_city=record_data.get('from_city', ''),
                from_state=record_data.get('from_state', ''),
                from_zip=record_data.get('from_zip', ''),
                from_phone=record_data.get('from_phone', ''),
                to_first_name=record_data.get('to_first_name', ''),
                to_last_name=record_data.get('to_last_name', ''),
                to_address1=record_data.get('to_address1', ''),
                to_address2=record_data.get('to_address2', ''),
                to_city=record_data.get('to_city', ''),
                to_state=record_data.get('to_state', ''),
                to_zip=record_data.get('to_zip', ''),
                to_phone=record_data.get('to_phone', ''),
                weight_lb=record_data.get('weight_lb'),
                weight_oz=record_data.get('weight_oz'),
                length=record_data.get('length'),
                width=record_data.get('width'),
                height=record_data.get('height'),
                order_number=record_data.get('order_number', ''),
                item_sku=record_data.get('item_sku', ''),
            )
            records.append(record)

        # Bulk create for performance
        ShipmentRecord.objects.bulk_create(records)

        # Now validate all records
        all_records = batch.records.all()# type: ignore
        stats = validate_records_bulk(all_records)

        # Bulk update validation fields
        ShipmentRecord.objects.bulk_update(
            all_records, ['validation_errors', 'is_valid']
        )

        # Update batch stats
        batch.total_records = stats['total']
        batch.valid_records = stats['valid']
        batch.invalid_records = stats['invalid']
        batch.save()

    logger.info(
        f"Batch #{batch.pk} created: {stats['total']} records "
        f"({stats['valid']} valid, {stats['invalid']} invalid)"
    )

    response_data = ShipmentBatchSerializer(batch).data
    if result['errors']:
        response_data['parse_warnings'] = result['errors']# type: ignore

    return Response(response_data, status=status.HTTP_201_CREATED)


# =============================================================================
# BATCH ENDPOINTS
# =============================================================================

@extend_schema(
    tags=['Batches'],
    responses={200: ShipmentBatchListSerializer(many=True)},
    description='List all batches for the current user.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def batch_list(request):
    batches = ShipmentBatch.objects.filter(user=request.user)
    serializer = ShipmentBatchListSerializer(batches, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=['Batches'],
    responses={200: ShipmentBatchSerializer},
    description='Get details for a specific batch.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def batch_detail(request, batch_id):
    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Recalculate stats in case records changed
    batch.recalculate_stats()
    serializer = ShipmentBatchSerializer(batch)
    return Response(serializer.data)


@extend_schema(
    tags=['Batches'],
    responses={204: None},
    description='Delete a batch and all its records.',
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def batch_delete(request, batch_id):
    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    if batch.status == ShipmentBatch.Status.PURCHASED:
        return Response(
            {'error': 'Cannot delete a purchased batch.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    batch.delete()
    logger.info(f"Batch #{batch_id} deleted by {request.user.username}")
    return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================================
# SHIPMENT RECORD ENDPOINTS
# =============================================================================

@extend_schema(
    tags=['Shipments'],
    responses={200: ShipmentRecordSerializer(many=True)},
    parameters=[
        OpenApiParameter(name='filter', description='Filter: all, valid, invalid', type=str),
        OpenApiParameter(name='search', description='Search by name, address, order number', type=str),
        OpenApiParameter(name='verification', description='Filter: unverified, verified, failed', type=str),
    ],
    description='List all shipment records in a batch with optional filtering and search.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shipment_list(request, batch_id):
    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    records = batch.records.all()# type: ignore

    # Filter by validity
    filter_param = request.query_params.get('filter', 'all')
    if filter_param == 'valid':
        records = records.filter(is_valid=True)
    elif filter_param == 'invalid':
        records = records.filter(is_valid=False)

    # Filter by verification status
    verification = request.query_params.get('verification', '')
    if verification in ['unverified', 'verified', 'failed']:
        records = records.filter(to_address_verified=verification)

    # Search
    search = request.query_params.get('search', '').strip()
    if search:
        from django.db.models import Q
        records = records.filter(
            Q(to_first_name__icontains=search) |
            Q(to_last_name__icontains=search) |
            Q(from_first_name__icontains=search) |
            Q(from_last_name__icontains=search) |
            Q(to_address1__icontains=search) |
            Q(from_address1__icontains=search) |
            Q(to_city__icontains=search) |
            Q(from_city__icontains=search) |
            Q(order_number__icontains=search) |
            Q(item_sku__icontains=search)
        )

    serializer = ShipmentRecordSerializer(records, many=True)
    return Response(serializer.data)


@extend_schema(
    tags=['Shipments'],
    responses={200: ShipmentRecordSerializer},
    description='Get a single shipment record.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shipment_detail(request, shipment_id):
    try:
        record = ShipmentRecord.objects.get(
            pk=shipment_id, batch__user=request.user
        )
    except ShipmentRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ShipmentRecordSerializer(record)
    return Response(serializer.data)


@extend_schema(
    tags=['Shipments'],
    request=ShipmentRecordUpdateSerializer,
    responses={200: ShipmentRecordSerializer},
    description='Update a shipment record. Re-validates after update.',
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def shipment_update(request, shipment_id):
    try:
        record = ShipmentRecord.objects.get(
            pk=shipment_id, batch__user=request.user
        )
    except ShipmentRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    if record.batch.status == ShipmentBatch.Status.PURCHASED:
        return Response(
            {'error': 'Cannot edit records in a purchased batch.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ShipmentRecordUpdateSerializer(record, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    # Re-validate after edit
    validate_and_update_record(record)

    # Reset verification status for changed address fields
    address_fields_from = ['from_first_name', 'from_last_name', 'from_address1',
                           'from_address2', 'from_city', 'from_state', 'from_zip']
    address_fields_to = ['to_first_name', 'to_last_name', 'to_address1',
                         'to_address2', 'to_city', 'to_state', 'to_zip']

    changed_fields = set(request.data.keys())
    if changed_fields & set(address_fields_from):
        record.from_address_verified = ShipmentRecord.VerificationStatus.UNVERIFIED
    if changed_fields & set(address_fields_to):
        record.to_address_verified = ShipmentRecord.VerificationStatus.UNVERIFIED

    # Recalculate shipping cost if service is set
    if record.shipping_service:
        record.shipping_cost = calculate_cost_for_record(record)

    record.save()

    # Recalculate batch stats
    record.batch.recalculate_stats()

    logger.info(f"Record #{shipment_id} updated by {request.user.username}")
    return Response(ShipmentRecordSerializer(record).data)


@extend_schema(
    tags=['Shipments'],
    responses={204: None},
    description='Delete a single shipment record.',
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def shipment_delete(request, shipment_id):
    try:
        record = ShipmentRecord.objects.get(
            pk=shipment_id, batch__user=request.user
        )
    except ShipmentRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    if record.batch.status == ShipmentBatch.Status.PURCHASED:
        return Response(
            {'error': 'Cannot delete records from a purchased batch.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    batch = record.batch
    record.delete()
    batch.recalculate_stats()

    logger.info(f"Record #{shipment_id} deleted by {request.user.username}")
    return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================================
# BULK ACTIONS
# =============================================================================

def _get_batch_records(user, batch_id, shipment_ids):
    """Helper to validate and fetch records for bulk actions."""
    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=user)
    except ShipmentBatch.DoesNotExist:
        return None, None, Response(
            {'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND
        )

    if batch.status == ShipmentBatch.Status.PURCHASED:
        return None, None, Response(
            {'error': 'Cannot modify a purchased batch.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    records = ShipmentRecord.objects.filter(
        batch=batch, pk__in=shipment_ids
    )

    if records.count() == 0:
        return None, None, Response(
            {'error': 'No matching records found.'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return batch, records, None


@extend_schema(
    tags=['Shipments'],
    request=BulkUpdateFromAddressSerializer,
    responses={200: ShipmentRecordSerializer(many=True)},
    description='Apply a saved address as Ship From to selected records.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_from_address(request, batch_id):
    serializer = BulkUpdateFromAddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    shipment_ids = serializer.validated_data['shipment_ids']# type: ignore
    saved_address_id = serializer.validated_data['saved_address_id']# type: ignore

    # Get the saved address
    try:
        saved_addr = SavedAddress.objects.get(pk=saved_address_id, user=request.user)
    except SavedAddress.DoesNotExist:
        return Response(
            {'error': 'Saved address not found.'}, status=status.HTTP_404_NOT_FOUND
        )

    batch, records, error = _get_batch_records(request.user, batch_id, shipment_ids)
    if error:
        return error

    # Apply saved address to all selected records
    with transaction.atomic():
        records.update(# type: ignore
            from_first_name=saved_addr.first_name,
            from_last_name=saved_addr.last_name,
            from_address1=saved_addr.address_line1,
            from_address2=saved_addr.address_line2,
            from_city=saved_addr.city,
            from_state=saved_addr.state,
            from_zip=saved_addr.zip_code,
            from_phone=saved_addr.phone,
            from_address_verified=ShipmentRecord.VerificationStatus.UNVERIFIED,
        )

        # Re-validate all affected records
        updated_records = ShipmentRecord.objects.filter(
            batch=batch, pk__in=shipment_ids
        )
        for record in updated_records:
            validate_and_update_record(record)
        ShipmentRecord.objects.bulk_update(
            updated_records, ['validation_errors', 'is_valid']
        )

        batch.recalculate_stats()# type: ignore

    count = records.count()# type: ignore
    logger.info(
        f"Bulk Ship From update: {count} records updated with address "
        f"'{saved_addr.label}' by {request.user.username}"
    )

    return Response({
        'message': f'Ship From address updated for {count} records.',
        'updated_count': count,
    })


@extend_schema(
    tags=['Shipments'],
    request=BulkUpdatePackageSerializer,
    responses={200: ShipmentRecordSerializer(many=True)},
    description='Apply a saved package preset to selected records.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_package(request, batch_id):
    serializer = BulkUpdatePackageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    shipment_ids = serializer.validated_data['shipment_ids']# type: ignore
    saved_package_id = serializer.validated_data['saved_package_id']# type: ignore

    # Get the saved package
    try:
        saved_pkg = SavedPackage.objects.get(pk=saved_package_id, user=request.user)
    except SavedPackage.DoesNotExist:
        return Response(
            {'error': 'Saved package not found.'}, status=status.HTTP_404_NOT_FOUND
        )

    batch, records, error = _get_batch_records(request.user, batch_id, shipment_ids)
    if error:
        return error

    # Apply saved package to all selected records
    with transaction.atomic():
        records.update(# type: ignore
            length=saved_pkg.length,
            width=saved_pkg.width,
            height=saved_pkg.height,
            weight_lb=saved_pkg.weight_lb,
            weight_oz=saved_pkg.weight_oz,
        )

        # Re-validate and recalculate shipping costs
        updated_records = ShipmentRecord.objects.filter(
            batch=batch, pk__in=shipment_ids
        )
        for record in updated_records:
            validate_and_update_record(record)
            if record.shipping_service:
                record.shipping_cost = calculate_cost_for_record(record)
        ShipmentRecord.objects.bulk_update(
            updated_records, ['validation_errors', 'is_valid', 'shipping_cost']
        )

        batch.recalculate_stats()# type: ignore

    count = records.count()# type: ignore
    logger.info(
        f"Bulk package update: {count} records updated with package "
        f"'{saved_pkg.label}' by {request.user.username}"
    )

    return Response({
        'message': f'Package details updated for {count} records.',
        'updated_count': count,
    })


@extend_schema(
    tags=['Shipments'],
    request=BulkUpdateShippingSerializer,
    description='Change shipping service for selected records.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_update_shipping(request, batch_id):
    serializer = BulkUpdateShippingSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    shipment_ids = serializer.validated_data['shipment_ids']# type: ignore
    service = serializer.validated_data['service']# type: ignore

    batch, records, error = _get_batch_records(request.user, batch_id, shipment_ids)
    if error:
        return error

    with transaction.atomic():
        updated_records = list(ShipmentRecord.objects.filter(
            batch=batch, pk__in=shipment_ids
        ))

        for record in updated_records:
            if service == 'cheapest':
                cheapest = get_cheapest_service(
                    record.weight_lb or 0, record.weight_oz or 0
                )
                record.shipping_service = cheapest['service']
                record.shipping_cost = cheapest['cost']
            else:
                record.shipping_service = service
                record.shipping_cost = calculate_cost_for_record(record)

        ShipmentRecord.objects.bulk_update(
            updated_records, ['shipping_service', 'shipping_cost']
        )

        batch.recalculate_stats()# type: ignore

    count = len(updated_records)
    logger.info(
        f"Bulk shipping update: {count} records changed to '{service}' "
        f"by {request.user.username}"
    )

    return Response({
        'message': f'Shipping service updated for {count} records.',
        'updated_count': count,
    })


@extend_schema(
    tags=['Shipments'],
    request=BulkDeleteSerializer,
    responses={204: None},
    description='Delete multiple shipment records.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete(request, batch_id):
    serializer = BulkDeleteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    shipment_ids = serializer.validated_data['shipment_ids']# type: ignore

    batch, records, error = _get_batch_records(request.user, batch_id, shipment_ids)
    if error:
        return error

    count = records.count()# type: ignore

    with transaction.atomic():
        records.delete()# type: ignore
        batch.recalculate_stats()# type: ignore

    logger.info(f"Bulk delete: {count} records from batch #{batch_id} by {request.user.username}")
    return Response(status=status.HTTP_204_NO_CONTENT)


# =============================================================================
# SHIPPING RATES
# =============================================================================

@extend_schema(
    tags=['Shipments'],
    description='Get available shipping services and their pricing.',
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shipping_rates(request):
    return Response({'services': get_available_services()})


@extend_schema(
    tags=['Shipments'],
    description='Assign default shipping service to all records in a batch and calculate costs.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def calculate_batch_rates(request, batch_id):
    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    default_service = request.data.get('default_service', 'ground')
    if default_service not in ['priority', 'ground']:
        return Response(
            {'error': 'Invalid service. Use "priority" or "ground".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Only calculate for valid records
    valid_records = list(batch.records.filter(is_valid=True)) # type: ignore
    skipped = batch.records.filter(is_valid=False).count() # type: ignore

    with transaction.atomic():
        for record in valid_records:
            if not record.shipping_service:
                record.shipping_service = default_service
            record.shipping_cost = calculate_cost_for_record(record)

        ShipmentRecord.objects.bulk_update(valid_records, ['shipping_service', 'shipping_cost'])

        # Reset cost for invalid records (in case they had old costs)
        batch.records.filter(is_valid=False).update(shipping_service='', shipping_cost=0) # type: ignore

        batch.recalculate_stats()

    logger.info(f"Batch #{batch_id} rates calculated: {len(valid_records)} priced, {skipped} skipped, total ${batch.total_cost}")

    return Response({
        'message': f'Rates calculated for {len(valid_records)} valid records. {skipped} invalid records skipped.',
        'priced_count': len(valid_records),
        'skipped_count': skipped,
        'total_cost': float(batch.total_cost),
    })
# =============================================================================
# PURCHASE
# =============================================================================

@extend_schema(
    tags=['Batches'],
    request=PurchaseSerializer,
    responses={200: PurchaseResponseSerializer},
    description='Finalize purchase for a batch. Deducts balance and creates transaction.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_batch(request, batch_id):
    serializer = PurchaseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Validations
    if batch.status == ShipmentBatch.Status.PURCHASED:
        return Response(
            {'error': 'This batch has already been purchased.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check all records are valid
    invalid_count = batch.records.filter(is_valid=False).count()# type: ignore
    if invalid_count > 0:
        return Response(
            {'error': f'{invalid_count} records are still invalid. Fix them before purchasing.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check all records have shipping service selected
    no_service = batch.records.filter(shipping_service='').count()# type: ignore
    if no_service > 0:
        return Response(
            {'error': f'{no_service} records have no shipping service selected.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Recalculate total to be safe
    batch.recalculate_stats()
    total_cost = batch.total_cost

    if total_cost <= 0:
        return Response(
            {'error': 'Total cost must be greater than zero.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Check balance
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.balance < total_cost:
        return Response(
            {
                'error': 'Insufficient balance.',
                'required': float(total_cost),
                'current_balance': float(profile.balance),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Process purchase
    with transaction.atomic():
        # Deduct balance
        profile.balance -= total_cost
        profile.save()

        # Update batch
        batch.status = ShipmentBatch.Status.PURCHASED
        batch.label_size = serializer.validated_data['label_size']# type: ignore
        batch.save()

        # Create transaction record
        Transaction.objects.create(
            user=request.user,
            batch=batch,
            type=Transaction.Type.PURCHASE,
            amount=total_cost,
            description=f'Purchased {batch.total_records} shipping labels (Batch #{batch.pk})',
        )

    logger.info(
        f"Purchase complete: Batch #{batch.pk}, {batch.total_records} labels, "
        f"${total_cost} by {request.user.username}"
    )

    return Response({
        'message': 'Purchase successful! Your shipping labels are being generated.',
        'batch_id': batch.pk,
        'total_labels': batch.total_records,
        'total_cost': float(total_cost),
        'label_size': batch.get_label_size_display(), # type: ignore
        'new_balance': float(profile.balance),
    })



"""
ADD THESE VIEWS TO THE BOTTOM OF apps/shipments/views.py
Also add this import at the top of views.py:

from .services.address_verifier import verify_record_address
"""


# =============================================================================
# ADDRESS VERIFICATION
# =============================================================================

@extend_schema(
    tags=['Shipments'],
    request=None,
    description='Verify an address on a shipment record. Pass address_type as "from" or "to" in the URL.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_address_view(request, shipment_id, address_type):
    """Verify a single address (from or to) on a shipment record."""

    if address_type not in ['from', 'to']:
        return Response(
            {'error': 'address_type must be "from" or "to".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        record = ShipmentRecord.objects.get(
            pk=shipment_id, batch__user=request.user
        )
    except ShipmentRecord.DoesNotExist:
        return Response({'error': 'Record not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Don't verify if record is invalid — user should fix errors first
    if not record.is_valid:
        return Response(
            {
                'error': 'Record has validation errors. Fix them before verifying.',
                'validation_errors': record.validation_errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Run verification
    result = verify_record_address(record, address_type)

    # Update verification status on the record
    if address_type == 'from':
        record.from_address_verified = (
            ShipmentRecord.VerificationStatus.VERIFIED if result['verified']
            else ShipmentRecord.VerificationStatus.FAILED
        )
    else:
        record.to_address_verified = (
            ShipmentRecord.VerificationStatus.VERIFIED if result['verified']
            else ShipmentRecord.VerificationStatus.FAILED
        )
    record.save()

    logger.info(
        f"Address verification ({address_type}) for record #{shipment_id}: "
        f"{'passed' if result['verified'] else 'failed'}"
    )

    return Response({
        'shipment_id': shipment_id,
        'address_type': address_type,
        'verified': result['verified'],
        'errors': result['errors'],
        'warnings': result['warnings'],
        'suggestions': result['suggestions'],
    })


@extend_schema(
    tags=['Shipments'],
    description='Bulk verify addresses for selected records. Only verifies records that are valid.',
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_verify_addresses(request, batch_id):
    """Verify addresses for multiple shipment records."""

    try:
        batch = ShipmentBatch.objects.get(pk=batch_id, user=request.user)
    except ShipmentBatch.DoesNotExist:
        return Response({'error': 'Batch not found.'}, status=status.HTTP_404_NOT_FOUND)

    shipment_ids = request.data.get('shipment_ids', [])
    address_type = request.data.get('address_type', 'to')

    if address_type not in ['from', 'to', 'both']:
        return Response(
            {'error': 'address_type must be "from", "to", or "both".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Get records — only valid ones
    records = ShipmentRecord.objects.filter(batch=batch, is_valid=True)
    if shipment_ids:
        records = records.filter(pk__in=shipment_ids)

    results = {
        'total': records.count(),
        'verified': 0,
        'failed': 0,
        'skipped': 0,
        'details': [],
    }

    records_to_update = []

    for record in records:
        record_result = {'shipment_id': record.pk, 'row_number': record.row_number}

        if address_type in ['to', 'both']:
            to_result = verify_record_address(record, 'to')
            record.to_address_verified = (
                ShipmentRecord.VerificationStatus.VERIFIED if to_result['verified']
                else ShipmentRecord.VerificationStatus.FAILED
            )
            record_result['to_verified'] = to_result['verified']
            record_result['to_warnings'] = to_result['warnings']

        if address_type in ['from', 'both']:
            from_result = verify_record_address(record, 'from')
            record.from_address_verified = (
                ShipmentRecord.VerificationStatus.VERIFIED if from_result['verified']
                else ShipmentRecord.VerificationStatus.FAILED
            )
            record_result['from_verified'] = from_result['verified']
            record_result['from_warnings'] = from_result['warnings']

        # Count results
        all_passed = True
        if address_type in ['to', 'both'] and not to_result['verified']:
            all_passed = False
        if address_type in ['from', 'both'] and not from_result['verified']:
            all_passed = False

        if all_passed:
            results['verified'] += 1
        else:
            results['failed'] += 1

        results['details'].append(record_result)
        records_to_update.append(record)

    # Bulk save
    update_fields = []
    if address_type in ['to', 'both']:
        update_fields.append('to_address_verified')
    if address_type in ['from', 'both']:
        update_fields.append('from_address_verified')

    if records_to_update and update_fields:
        ShipmentRecord.objects.bulk_update(records_to_update, update_fields)

    # Count skipped (invalid records that weren't verified)
    if shipment_ids:
        total_requested = len(shipment_ids)
    else:
        total_requested = batch.records.count() # type: ignore
    results['skipped'] = total_requested - results['total']

    logger.info(
        f"Bulk verify ({address_type}) for batch #{batch_id}: "
        f"{results['verified']} verified, {results['failed']} failed, "
        f"{results['skipped']} skipped"
    )

    return Response(results)