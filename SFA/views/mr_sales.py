import json
from datetime import datetime
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from SFA.models import Stockist, Product, PrimarySale, StockistProductStatement

# ==============================================================================
# 📦 MR PRIMARY SALE ENTRY (Cart / Bulk Upload Mode)
# ==============================================================================
@login_required
def mr_primary_sale_entry(request):
    emp = request.user.employee
    
    if not hasattr(emp.company, 'settings') or not emp.company.settings.allow_mr_primary_sale:
        messages.error(request, "Primary Sale entry is currently disabled for MRs. Please contact Admin.")
        return redirect('request_hub')

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            stockist_id = data.get('stockist')
            batch_number = data.get('batch_number', 'N/A')
            items = data.get('items', [])

            if not items:
                return JsonResponse({'status': 'error', 'message': 'No products added to the invoice!'})

            stockist = get_object_or_404(Stockist, id=stockist_id, company=emp.company)
            
            # String date ko datetime object mein convert karein
            sale_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # 🌟 BULK SAVE: Products save karein aur Statement Update karein
            # 🚀 N+1 FIXED (API twin pattern): saare products EK query + bulk creates
            product_ids = [item['product_id'] for item in items]
            products_dict = {p.id: p for p in Product.objects.filter(
                id__in=product_ids, company=emp.company
            )}

            # 🚀 Existing statements EK query
            existing_stats = {
                stat.product_id: stat for stat in StockistProductStatement.objects.filter(
                    employee=emp, stockist=stockist, product_id__in=product_ids,
                    month=sale_date.month, year=sale_date.year
                )
            }

            sales_to_create = []
            stats_to_create = []
            stats_to_update = []

            for item in items:
                product = products_dict.get(item['product_id'])
                if not product:
                    return JsonResponse({'status': 'error', 'message': f"Invalid product in invoice: {item['product_id']}"})

                try:
                    billed_qty = int(item['quantity'])
                    free_qty = int(item['free_qty'])
                except (TypeError, ValueError):
                    return JsonResponse({'status': 'error', 'message': 'Invalid quantity values in invoice!'})

                sales_to_create.append(PrimarySale(
                    date=sale_date, stockist=stockist, product=product,
                    quantity=billed_qty, free_quantity=free_qty, batch_number=batch_number
                ))

                stat = existing_stats.get(product.id)
                if stat:
                    stat.received_qty += (billed_qty + free_qty)
                    stats_to_update.append(stat)
                else:
                    stats_to_create.append(StockistProductStatement(
                        employee=emp, stockist=stockist, product=product,
                        month=sale_date.month, year=sale_date.year,
                        received_qty=(billed_qty + free_qty)
                    ))

            # 🛡️ TRANSACTION + 🚀 3 bulk queries (40 → ~5)
            from django.db import transaction
            with transaction.atomic():
                PrimarySale.objects.bulk_create(sales_to_create)
                if stats_to_update:
                    StockistProductStatement.objects.bulk_update(stats_to_update, ['received_qty'])
                if stats_to_create:
                    StockistProductStatement.objects.bulk_create(stats_to_create)

            messages.success(request, f"✅ Invoice with {len(items)} products uploaded successfully for {stockist.name}!")
            return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    # GET Request (Page Load)
    stockists = Stockist.objects.filter(company=emp.company, territory=emp.headquarter)
    products = Product.objects.filter(company=emp.company)
    
    context = {
        'stockists': stockists,
        'products': products,
        'today': timezone.now().date(),
    }
    return render(request, 'mr_primary_sale.html', context)
