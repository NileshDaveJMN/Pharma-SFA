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
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from datetime import date, timedelta
from SFA.models import Stockist, FocusProductTracking, WeeklyStockistSaleMaster, WeeklyStockistSaleDetail

def weekly_secondary_sale_view(request):
    employee = request.user.employee
    company = employee.company
    
    # 🕒 TIME RESTRICTION & DATE CALCULATION LOGIC
    today = date.today()
    weekday = today.weekday() # 0:Mon, 1:Tue, 2:Wed, 3:Thu, 4:Fri, 5:Sat, 6:Sun
    
    if weekday == 5: # Saturday
        last_saturday = today
    elif weekday == 6: # Sunday
        last_saturday = today - timedelta(days=1)
    elif weekday == 0: # Monday
        last_saturday = today - timedelta(days=2)
    else:
        # Tuesday to Friday (Locked Days) - Calculate previous Saturday just to show on screen
        days_since_saturday = (weekday + 2) % 7
        last_saturday = today - timedelta(days=days_since_saturday)
        
    is_locked = weekday not in [0, 5, 6] # Entry allowed ONLY on Mon(0), Sat(5), Sun(6)
    
    stockists = Stockist.objects.filter(territory=employee.headquarter, company=company)
    focus_products = FocusProductTracking.objects.filter(company=company, is_active=True).select_related('product')
    
    # 🔄 AJAX GET: Form Auto-fill (Jab MR dropdown se stockist select karega)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' and request.method == 'GET':
        stockist_id = request.GET.get('stockist_id')
        if stockist_id:
            try:
                master = WeeklyStockistSaleMaster.objects.get(
                    employee=employee, 
                    stockist_id=stockist_id, 
                    week_ending_date=last_saturday
                )
                details = WeeklyStockistSaleDetail.objects.filter(master=master)
                
                details_data = {d.product.id: {'sec_qty': d.sec_sale_qty, 'closing_qty': d.closing_qty} for d in details}
                
                return JsonResponse({
                    'success': True,
                    'total_sec': master.total_sec_sale_value,
                    'total_closing': master.total_closing_value,
                    'details': details_data
                })
            except WeeklyStockistSaleMaster.DoesNotExist:
                return JsonResponse({'success': False}) # Agar nayi entry hai
                
    # 💾 POST REQUEST: Data Save/Update karna
    if request.method == 'POST':
        if is_locked:
            messages.error(request, "Entry locked! Data submission for the previous week is only permitted on Saturdays, Sundays, and Mondays.")
            return redirect('weekly_secondary_sale')

            return redirect('weekly_secondary_sale')
            
        stockist_id = request.POST.get('stockist_id')
        total_sec = request.POST.get('total_sec_sale_value', 0)
        total_closing = request.POST.get('total_closing_value', 0)
        
        if not stockist_id:
            messages.error(request, "Kripya ek Stockist select karein.")
            return redirect('weekly_secondary_sale')
            
        # 1. Master Record Update ya Create karo
        master, created = WeeklyStockistSaleMaster.objects.update_or_create(
            company=company,
            employee=employee,
            stockist_id=stockist_id,
            week_ending_date=last_saturday,
            defaults={
                'total_sec_sale_value': total_sec or 0,
                'total_closing_value': total_closing or 0
            }
        )
        
        # 2. Purane product details hata do (taaki edit karne par duplicate data na bane)
        WeeklyStockistSaleDetail.objects.filter(master=master).delete()
        
        # 3. Naye product details save karo
        for fp in focus_products:
            pid = fp.product.id
            sec_qty = request.POST.get(f'sec_qty_{pid}', 0)
            closing_qty = request.POST.get(f'closing_qty_{pid}', 0)
            
            # Agar value daali hai tabhi save karega
            if sec_qty or closing_qty: 
                WeeklyStockistSaleDetail.objects.create(
                    master=master,
                    product_id=pid,
                    sec_sale_qty=sec_qty or 0,
                    closing_qty=closing_qty or 0
                )
        
        messages.success(request, f"Data for week ending {last_saturday.strftime('%d-%b-%Y')} saved successfully!")
        return redirect('weekly_secondary_sale')
        
    context = {
        'stockists': stockists,
        'focus_products': focus_products,
        'target_date': last_saturday,
        'is_locked': is_locked,
    }
    return render(request, 'weekly_sale_entry.html', context)
