from django.shortcuts import render, redirect
from django.contrib import messages
from SFA.models import Product, FocusProductTracking, CampaignControl # CampaignControl import kiya

def manage_focus_products(request):
    employee = request.user.employee
    company = employee.company

    # 1. RSM ka current toggle status fetch karna
    control, created = CampaignControl.objects.get_or_create(manager=employee)

    if request.method == 'POST':
        # Action check karna (Toggle switch dabaya hai ya Save button?)
        action = request.POST.get('action')

        if action == 'toggle_campaign':
            # Toggle state ko ulta (ON ko OFF, OFF ko ON) kar do
            control.is_weekly_focus_active = not control.is_weekly_focus_active
            control.save()
            status_text = "Activated" if control.is_weekly_focus_active else "Deactivated"
            messages.info(request, f"Secondary Sales Campaign is now {status_text} for your team.")
            return redirect('manage_focus_products')

        elif action == 'save_products' and control.is_weekly_focus_active:
            # Agar Save button dabaya hai aur campaign ON hai tabhi save hoga
            selected_product_ids = request.POST.getlist('focus_products')
            selected_product_ids = [int(pid) for pid in selected_product_ids]

            FocusProductTracking.objects.filter(company=company, added_by=employee).update(is_active=False)

            for pid in selected_product_ids:
                FocusProductTracking.objects.update_or_create(
                    company=company,
                    product_id=pid,
                    added_by=employee,
                    defaults={'is_active': True}
                )
            
            messages.success(request, "Focus Products updated successfully!")
            return redirect('manage_focus_products')

    # GET Request Logic
    all_products = Product.objects.filter(company=company).order_by('name')
    active_focus_ids = FocusProductTracking.objects.filter(
        company=company, added_by=employee, is_active=True
    ).values_list('product_id', flat=True)

    context = {
        'all_products': all_products,
        'active_focus_ids': list(active_focus_ids),
        'is_campaign_active': control.is_weekly_focus_active, # Template me bhejne ke liye
    }
    return render(request, 'focus_products.html', context)
