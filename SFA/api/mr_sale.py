from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime
from SFA.models import Stockist, Product, PrimarySale, StockistProductStatement

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_primary_sale_data(request):
    emp = request.user.employee
    if not hasattr(emp.company, 'settings') or not emp.company.settings.allow_mr_primary_sale:
        return Response({'status': 'error', 'message': 'Primary Sale entry is disabled for MRs.'}, status=403)

    stockists = Stockist.objects.filter(company=emp.company, territory=emp.headquarter).values('id', 'name')
    products = Product.objects.filter(company=emp.company).values('id', 'name')
    
    return Response({
        'status': 'success',
        'stockists': list(stockists),
        'products': list(products)
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_submit_primary_sale(request):
    emp = request.user.employee
    if not hasattr(emp.company, 'settings') or not emp.company.settings.allow_mr_primary_sale:
        return Response({'status': 'error', 'message': 'Primary Sale entry is disabled for MRs.'}, status=403)

    data = request.data
    date_str = data.get('date')
    stockist_id = data.get('stockist')
    batch_number = data.get('batch_number', 'N/A')
    items = data.get('items', [])

    if not items:
        return Response({'status': 'error', 'message': 'No products added to the invoice!'}, status=400)

    try:
        stockist = get_object_or_404(Stockist, id=stockist_id, company=emp.company)
        sale_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # 🚀 OPTIMIZATION 1: Saare products 1 query mein Memory mein load karein
        product_ids = [item['product_id'] for item in items]
        products_dict = {p.id: p for p in Product.objects.filter(id__in=product_ids, company=emp.company)}

        # 🚀 OPTIMIZATION 2: Saare existing statements 1 query mein fetch karein
        existing_stats = {
            stat.product_id: stat for stat in StockistProductStatement.objects.filter(
                employee=emp, stockist=stockist, product_id__in=product_ids, 
                month=sale_date.month, year=sale_date.year
            )
        }

        sales_to_create = []
        stats_to_create = []
        stats_to_update = []

        # RAM ke andar list banayenge (No DB calls here)
        for item in items:
            p_id = item['product_id']
            if p_id not in products_dict: continue
                
            product = products_dict[p_id]
            billed_qty = int(item['quantity'])
            free_qty = int(item['free_qty'])
            total_qty = billed_qty + free_qty
            
            sales_to_create.append(PrimarySale(
                date=sale_date, stockist=stockist, product=product,
                quantity=billed_qty, free_quantity=free_qty, batch_number=batch_number
            ))
            
            stat = existing_stats.get(p_id)
            if stat:
                stat.received_qty += total_qty
                stats_to_update.append(stat)
            else:
                stats_to_create.append(StockistProductStatement(
                    employee=emp, stockist=stockist, product=product,
                    month=sale_date.month, year=sale_date.year, received_qty=total_qty
                ))

        # 🚀 OPTIMIZATION 3: Bulk Operations (200 queries reduce hoke sirf 3 queries ban gayi!)
        with transaction.atomic():
            if sales_to_create:
                PrimarySale.objects.bulk_create(sales_to_create)
            if stats_to_update:
                StockistProductStatement.objects.bulk_update(stats_to_update, ['received_qty'])
            if stats_to_create:
                StockistProductStatement.objects.bulk_create(stats_to_create)
                
        return Response({
            'status': 'success', 
            'message': f'✅ Invoice uploaded successfully for {stockist.name}'
        })

    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)
