import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from SFA.models import Stockist, Product, PrimarySale

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
            # 🌟 NAYA: JavaScript se aane wale JSON data ko read karna
            data = json.loads(request.body)
            date = data.get('date')
            stockist_id = data.get('stockist')
            batch_number = data.get('batch_number', 'N/A')
            items = data.get('items', [])

            if not items:
                return JsonResponse({'status': 'error', 'message': 'No products added to the invoice!'})

            stockist = get_object_or_404(Stockist, id=stockist_id, company=emp.company)

            # 🌟 BULK SAVE: Ek loop chala kar saare products save karna
            for item in items:
                product = get_object_or_404(Product, id=item['product_id'], company=emp.company)
                PrimarySale.objects.create(
                    date=date,
                    stockist=stockist,
                    product=product,
                    quantity=int(item['quantity']),
                    free_quantity=int(item['free_qty']),
                    batch_number=batch_number
                )
            
            # Message session mein daal kar success response bhejna
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
