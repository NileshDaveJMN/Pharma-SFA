from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from datetime import datetime
from SFA.models import Stockist, Product, PrimarySale, StockistProductStatement

# ==============================================================================
# 📦 1. GET INITIAL DATA (Flutter Dropdowns ke liye)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_primary_sale_data(request):
    emp = request.user.employee
    
    # Check if Primary Sale is allowed for MR
    if not hasattr(emp.company, 'settings') or not emp.company.settings.allow_mr_primary_sale:
        return Response({'status': 'error', 'message': 'Primary Sale entry is disabled for MRs.'}, status=403)

    # Flutter mein dropdown dikhane ke liye Stockists aur Products fetch karna
    stockists = Stockist.objects.filter(company=emp.company, territory=emp.headquarter).values('id', 'name')
    products = Product.objects.filter(company=emp.company).values('id', 'name')
    
    return Response({
        'status': 'success',
        'stockists': list(stockists),
        'products': list(products)
    })


# ==============================================================================
# 📤 2. SUBMIT INVOICE CART (Flutter se data save karna)
# ==============================================================================
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

        # 🌟 transaction.atomic() ensure karega ki ya toh poora bill save ho, ya kuch bhi nahi (error aane par)
        with transaction.atomic():
            for item in items:
                product = get_object_or_404(Product, id=item['product_id'], company=emp.company)
                billed_qty = int(item['quantity'])
                free_qty = int(item['free_qty'])
                
                # 1. Save Primary Sale Record
                PrimarySale.objects.create(
                    date=sale_date,
                    stockist=stockist,
                    product=product,
                    quantity=billed_qty,
                    free_quantity=free_qty,
                    batch_number=batch_number
                )
                
                # 2. Update Monthly Inventory Statement
                stat, _ = StockistProductStatement.objects.get_or_create(
                    employee=emp, stockist=stockist, product=product, 
                    month=sale_date.month, year=sale_date.year
                )
                stat.received_qty += (billed_qty + free_qty)
                stat.save()
                
        return Response({
            'status': 'success', 
            'message': f'✅ Invoice uploaded successfully for {stockist.name}'
        })

    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)
