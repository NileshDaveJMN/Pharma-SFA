from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from SFA.models import Stockist, Product, PrimarySale

# ==============================================================================
# 📦 MR PRIMARY SALE ENTRY (Add/Append Mode)
# ==============================================================================
@login_required
def mr_primary_sale_entry(request):
    emp = request.user.employee
    
    # 🛑 Check if Admin has allowed MRs to enter Primary Sale
    if not hasattr(emp.company, 'settings') or not emp.company.settings.allow_mr_primary_sale:
        messages.error(request, "Primary Sale entry is currently disabled for MRs. Please contact Admin.")
        return redirect('request_hub')

    # Fetch only relevant stockists and products
    stockists = Stockist.objects.filter(company=emp.company, territory=emp.headquarter)
    products = Product.objects.filter(company=emp.company)

    if request.method == 'POST':
        date = request.POST.get('date')
        stockist_id = request.POST.get('stockist')
        product_id = request.POST.get('product')
        quantity = int(request.POST.get('quantity', 0))
        free_qty = int(request.POST.get('free_quantity', 0))
        batch_number = request.POST.get('batch_number', 'N/A')

        if quantity > 0:
            stockist = get_object_or_404(Stockist, id=stockist_id, company=emp.company)
            product = get_object_or_404(Product, id=product_id, company=emp.company)
            
            # 🌟 APPENDING NEW RECORD (Transactional Entry)
            PrimarySale.objects.create(
                date=date,
                stockist=stockist,
                product=product,
                quantity=quantity,
                free_quantity=free_qty,
                batch_number=batch_number
            )
            messages.success(request, f"Successfully added {quantity} units of {product.name} for {stockist.name}.")
            return redirect('mr_primary_sale_entry')
        else:
            messages.error(request, "Quantity must be greater than zero.")

    context = {
        'stockists': stockists,
        'products': products,
        'today': timezone.now().date(),
    }
    return render(request, 'mr_primary_sale.html', context)
