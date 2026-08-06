from django.shortcuts import render, redirect
from django.contrib import messages
from SFA.models import Product, FocusProductTracking

def manage_focus_products(request):
    employee = request.user.employee
    company = employee.company

    # Sirf RSM ya upar ke level ke liye access (Optional check)
    # if employee.designation.lower() not in ['rsm', 'zsm', 'admin']:
    #     messages.error(request, "Access Denied!")
    #     return redirect('dashboard')

    if request.method == 'POST':
        # Form se checked products ki list nikalna
        selected_product_ids = request.POST.getlist('focus_products')
        selected_product_ids = [int(pid) for pid in selected_product_ids]

        # Step 1: Sabko temporarily de-activate kar do
        FocusProductTracking.objects.filter(company=company).update(is_active=False)

        # Step 2: Jo check kiye gaye hain, unko activate/create kar do
        for pid in selected_product_ids:
            FocusProductTracking.objects.update_or_create(
                company=company,
                product_id=pid,
                defaults={'is_active': True, 'added_by': employee}
            )
        
        messages.success(request, "Focus Products updated successfully!")
        return redirect('manage_focus_products')

    # GET Request: UI dikhane ke liye data fetch karna
    all_products = Product.objects.filter(company=company).order_by('name')
    
    # Jo products already focus list me hain unki ID nikal rahe hain (Checkbox pre-check karne ke liye)
    active_focus_ids = FocusProductTracking.objects.filter(
        company=company, is_active=True
    ).values_list('product_id', flat=True)

    context = {
        'all_products': all_products,
        'active_focus_ids': list(active_focus_ids),
    }
    return render(request, 'focus_products.html', context)
