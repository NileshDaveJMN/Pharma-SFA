from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from datetime import date, timedelta
import calendar
from SFA.models import Product, FocusProductTracking, CampaignControl
from SFA.models import Stockist, WeeklyStockistSaleMaster, WeeklyStockistSaleDetail
from .auth import get_dropdown_team


def manage_focus_products(request):
    employee = request.user.employee
    company = employee.company

    # 1. RSM ka current toggle status fetch karna
    control, created = CampaignControl.objects.get_or_create(manager=employee)

    if request.method == 'POST':
        # Action check: Toggle switch dabaya hai ya Save button?
        action = request.POST.get('action')

        if action == 'toggle_campaign':
            control.is_weekly_focus_active = not control.is_weekly_focus_active
            control.save()
            status_text = "Activated" if control.is_weekly_focus_active else "Deactivated"
            messages.info(request, f"Secondary Sales Campaign is now {status_text} for your team.")
            return redirect('manage_focus_products')

        elif action == 'save_products' and control.is_weekly_focus_active:
            # 🚀 N+1 FIXED: update_or_create loop ki jagah — deactivate + bulk_create
            selected_product_ids = request.POST.getlist('focus_products')
            selected_ids = []
            for pid in selected_product_ids:
                try:
                    selected_ids.append(int(pid))
                except (TypeError, ValueError):
                    continue

            # 🛡️ TRANSACTION: sab ya kuch nahi
            from django.db import transaction
            with transaction.atomic():
                FocusProductTracking.objects.filter(
                    company=company, added_by=employee
                ).update(is_active=False)

                if selected_ids:
                    # 🚀 Sirf VALID products hi save hon (company-scoped)
                    valid_products = Product.objects.filter(
                        id__in=selected_ids, company=company
                    ).values_list('id', flat=True)
                    FocusProductTracking.objects.bulk_create([
                        FocusProductTracking(
                            company=company, product_id=pid,
                            added_by=employee, is_active=True
                        ) for pid in valid_products
                    ])

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
        'is_campaign_active': control.is_weekly_focus_active,
    }
    return render(request, 'focus_products.html', context)


def weekly_secondary_sale_view(request):
    employee = request.user.employee
    company = employee.company

    # 🕒 TIME RESTRICTION & DATE CALCULATION LOGIC
    today = date.today()
    weekday = today.weekday()  # 0:Mon, 1:Tue, 2:Wed, 3:Thu, 4:Fri, 5:Sat, 6:Sun

    if weekday == 5:  # Saturday
        last_saturday = today
    elif weekday == 6:  # Sunday
        last_saturday = today - timedelta(days=1)
    elif weekday == 0:  # Monday
        last_saturday = today - timedelta(days=2)
    else:
        # Tuesday to Friday (Locked Days) — calculate previous Saturday for display
        days_since_saturday = (weekday + 2) % 7
        last_saturday = today - timedelta(days=days_since_saturday)

    is_locked = weekday not in [0, 5, 6]  # Entry allowed ONLY on Mon(0), Sat(5), Sun(6)

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
                return JsonResponse({'success': False})  # Agar nayi entry hai

    # 💾 POST REQUEST: Data Save/Update karna
    if request.method == 'POST':
        if is_locked:
            # 🌟 English message (pehle Hindi-style tha)
            messages.error(request, "Entry locked! Data submission for the previous week is only permitted on Saturdays, Sundays, and Mondays.")
            return redirect('weekly_secondary_sale')

        stockist_id = request.POST.get('stockist_id')
        total_sec = request.POST.get('total_sec_sale_value', 0)
        total_closing = request.POST.get('total_closing_value', 0)

        if not stockist_id:
            # 🌟 English message (pehle 'Kripya ek Stockist select karein.' tha)
            messages.error(request, "Please select a Stockist to continue.")
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

        # 2. Purane product details hata do (duplicate data na bane)
        WeeklyStockistSaleDetail.objects.filter(master=master).delete()

        # 🚀 N+1 FIXED: details list banao phir EK bulk_create (pehle loop mein INSERT tha)
        details_to_create = []
        for fp in focus_products:
            pid = fp.product.id
            sec_qty = request.POST.get(f'sec_qty_{pid}', 0) or 0
            closing_qty = request.POST.get(f'closing_qty_{pid}', 0) or 0

            if sec_qty or closing_qty:
                details_to_create.append(WeeklyStockistSaleDetail(
                    master=master,
                    product_id=pid,
                    sec_sale_qty=sec_qty,
                    closing_qty=closing_qty
                ))

        if details_to_create:
            WeeklyStockistSaleDetail.objects.bulk_create(details_to_create)

        messages.success(request, f"Data for week ending {last_saturday.strftime('%d-%b-%Y')} saved successfully!")
        return redirect('weekly_secondary_sale')

    context = {
        'stockists': stockists,
        'focus_products': focus_products,
        'target_date': last_saturday,
        'is_locked': is_locked,
    }
    return render(request, 'weekly_sale_entry.html', context)


# ==============================================================================
# 📊 WEEKLY SALE HISTORY (View-only report — MR: apna, Manager: puri team)
# ==============================================================================
def weekly_sale_history_view(request):
    employee = request.user.employee
    company = employee.company

    today = date.today()
    try:
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        month, year = today.month, today.year

    is_manager_view = employee.designation != 'MR'

    # 🌟 MR: sirf khud ka data. Manager: puri team ka (sub-team bhi shaamil)
    if is_manager_view:
        team_employees = get_dropdown_team(employee, ordered=False)
        team_ids = list(team_employees.values_list('id', flat=True))
        if employee.id not in team_ids:
            team_ids.append(employee.id)
    else:
        team_ids = [employee.id]

    records = WeeklyStockistSaleMaster.objects.filter(
        company=company,
        employee_id__in=team_ids,
        week_ending_date__month=month,
        week_ending_date__year=year
    ).select_related('employee', 'stockist').order_by('employee__name', 'week_ending_date', 'stockist__name')

    # Manager view ke liye employee-wise grouping + subtotal
    grouped = {}
    for r in records:
        grp = grouped.setdefault(r.employee.name, {'rows': [], 'subtotal': 0.0})
        grp['rows'].append(r)
        grp['subtotal'] += float(r.total_sec_sale_value or 0)

    # Prev/Next month navigation
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    context = {
        'is_manager_view': is_manager_view,
        'records': records,
        'grouped': grouped,
        'month': month,
        'year': year,
        'month_name': calendar.month_name[month],
        'prev_month': prev_month, 'prev_year': prev_year,
        'next_month': next_month, 'next_year': next_year,
    }
    return render(request, 'weekly_sale_history.html', context)