import calendar
from datetime import date, datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from SFA.models import MonthlyExpenseReport, DailyExpense, DailyDCR, DayStart, DayEnd, DARate, TARate, HQDistance
from .auth import get_full_team_employees
from SFA.decorators import employee_required

from django.contrib import messages # 🌟 NAYA: Ise top imports mein zaroor rakhein

def _save_misc_claims(mr, post_data):
    """Daily lines ke Misc amount aur Remark POST data se save karta hai. Save aur Submit dono se reuse hota hai."""
    for line in mr.daily_lines.all():
        lid = str(line.id)
        line.misc_amount = float(post_data.get(f'misc_{lid}', 0.00) or 0.00)
        line.remark      = post_data.get(f'remark_{lid}', '')
        line.save()


@employee_required
def expense_hub_view(request, employee):
    current_year = datetime.today().year
    today        = timezone.now().date()

    # ── Save Misc/TA — Draft aur Rejected dono allow ─────────────────
    if request.method == 'POST' and request.POST.get('action') == 'bulk_save_claims':
        mr = get_object_or_404(MonthlyExpenseReport, id=request.POST.get('report_id'), employee=employee)
        if mr.status in ('Draft', 'Rejected'):
            _save_misc_claims(mr, request.POST)
            messages.warning(request, "📝 Changes Draft mein SAVE ho gaye hain — par abhi tak SUBMIT nahi hua! Manager ko ye approval ke liye nahi dikhega jab tak aap neeche 'Submit for Approval' button na dabayein.")
        return redirect(f'/expense/?active_report={mr.id}')

    # ── Submit for approval (Draft ya Rejected → Pending) ────────────
    if request.method == 'POST' and request.POST.get('action') == 'submit_for_approval':
        rep_id = request.POST.get('report_id')
        mr = get_object_or_404(MonthlyExpenseReport, id=rep_id, employee=employee)
        
        # 🌟 STRICT RULE: Current month expense blocker
        if mr.year > today.year or (mr.year == today.year and mr.month >= today.month):
            messages.error(request, "⚠️ Current month ka expense abhi chal raha hai! Ise sirf mahina khatam hone ke baad (agle mahine) hi submit kiya ja sakta hai.")
            return redirect('expense_hub')

        if mr.status in ('Draft', 'Rejected'):
            _save_misc_claims(mr, request.POST)  # 🌟 Submit se pehle current Misc/Remark bhi save ho jaaye, kuch chhutna nahi chahiye
            _fill_missing_dates(mr, employee)
            mr.status         = 'Pending'
            mr.manager_remark = ''
            mr.is_modified    = False
            mr.save()
            messages.success(request, "✅ Expense Report successfully submitted for approval.")
        return redirect('expense_hub')

    # ── Reopen Rejected → Draft ───────────────────────────────────────
    if request.method == 'POST' and request.POST.get('action') == 'reopen_rejected':
        rep_id = request.POST.get('report_id')
        MonthlyExpenseReport.objects.filter(
            id=rep_id, employee=employee, status='Rejected'
        ).update(status='Draft')
        messages.info(request, "📝 Report ko wapas Draft mein daal diya gaya hai. Ab aap isme changes kar sakte hain.")
        return redirect(f'/expense/?active_report={rep_id}')

    # ── GET: load active report ───────────────────────────────────────
    active_rep_id = request.GET.get('active_report')
    active_report, daily_lines, grand_total = None, [], 0.00

    if active_rep_id:
        active_report = MonthlyExpenseReport.objects.filter(
            id=active_rep_id, employee=employee
        ).first()
        
        # 🌟 SMART RECOVERY: MR ke Claim Report open karte hi missing/deleted dates recover ho jayengi!
        if active_report and active_report.status in ['Draft', 'Rejected']:
            _fill_missing_dates(active_report, employee)
            
        if active_report:
            daily_lines = active_report.daily_lines.all().order_by('date')
            grand_total = sum(
                float((l.approved_ta   if l.approved_ta   is not None else l.ta_amount) +
                      (l.approved_da   if l.approved_da   is not None else l.da_amount) +
                      (l.approved_misc if l.approved_misc is not None else l.misc_amount))
                for l in daily_lines
            )

    return render(request, 'expense_hub.html', {
        'current_year':  current_year,
        'today':         today,
        'my_reports':    MonthlyExpenseReport.objects.filter(employee=employee).order_by('-year', '-month'),
        'active_report': active_report,
        'daily_lines':   daily_lines,
        'grand_total':   round(grand_total, 2),
    })

def calculate_missing_expense(emp, ds_obj):
    """Core logic se copy kiya hua function taaki missing expense exactly waisa hi recover ho sake"""
    routes = ds_obj.routes.select_related('territory').all()
    night_stay = ds_obj.night_stay

    from datetime import timedelta
    yesterday_ds = DayStart.objects.filter(employee=emp, date=ds_obj.date - timedelta(days=1)).first()
    is_prev_night_stay = yesterday_ds.night_stay if yesterday_ds else False
    is_return_day = is_prev_night_stay and not night_stay

    if is_prev_night_stay and yesterday_ds.territory: start_hq = yesterday_ds.territory
    else: start_hq = emp.headquarter

    max_total = 0.0
    best_local = 0.0
    best_transit = 0.0
    is_outside_hq = False 
    
    for r in routes:
        local_dist = float(r.distance_from_hq or 0)
        transit_dist = 0.0
        work_hq = r.territory

        if emp.headquarter and work_hq and emp.headquarter != work_hq: is_outside_hq = True

        if start_hq and work_hq and start_hq != work_hq:
            hq_conn = HQDistance.objects.filter(from_territory=start_hq, to_territory=work_hq).first()
            if not hq_conn: hq_conn = HQDistance.objects.filter(from_territory=work_hq, to_territory=start_hq).first()
            transit_dist += float(hq_conn.distance_km) if hq_conn else 0.0

        if is_return_day and work_hq and emp.headquarter and work_hq != emp.headquarter:
            hq_conn_ret = HQDistance.objects.filter(from_territory=work_hq, to_territory=emp.headquarter).first()
            if not hq_conn_ret: hq_conn_ret = HQDistance.objects.filter(from_territory=emp.headquarter, to_territory=work_hq).first()
            transit_dist += float(hq_conn_ret.distance_km) if hq_conn_ret else 0.0

        route_total = local_dist + transit_dist
        if route_total > max_total:
            max_total = route_total
            best_local = local_dist
            best_transit = transit_dist
            
    distance = max_total
    raw_cat = max((r.category for r in routes), key=lambda x: {'OUTSTATION': 3, 'EX_HQ': 2, 'HQ': 1}.get(x, 0)) if routes.exists() else 'HQ'

    if is_outside_hq: raw_cat = 'OUTSTATION' if night_stay or is_prev_night_stay else 'EX_HQ'

    if raw_cat == 'OUTSTATION':
        if is_return_day or (not night_stay and not is_prev_night_stay): eff_cat = 'EX_HQ'       
        else: eff_cat = 'OUTSTATION'  
    else: eff_cat = raw_cat

    try:
        da_rate = DARate.objects.get(company=emp.company, designation=emp.designation)
        da = {'HQ': da_rate.hq_da, 'EX_HQ': da_rate.exhq_da, 'OUTSTATION': da_rate.outstation_da}[eff_cat]
    except DARate.DoesNotExist: da = 0

    if not routes.exists() or eff_cat == 'HQ':
        return {'da': round(float(da), 2), 'ta': 0, 'distance': 0, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}

    changed_city_today = any(r.territory != start_hq for r in routes) if start_hq else False

    if is_return_day or (eff_cat == 'OUTSTATION' and night_stay and not is_prev_night_stay): transit_multiplier = 1
    elif eff_cat == 'OUTSTATION' and night_stay and is_prev_night_stay: transit_multiplier = 1 if changed_city_today else 0
    else: transit_multiplier = 2

    # 🌟 ASLI FIX: local (ex-station) distance hamesha round-trip — day-type se independent
    billed_distance = (best_local * 2) + (best_transit * transit_multiplier)

    try:
        ta_rate = TARate.objects.get(company=emp.company, designation=emp.designation)
        if billed_distance == 0: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
        elif distance <= ta_rate.slab1_upto_km: ta = round(billed_distance * float(ta_rate.slab1_rate), 2)
        elif distance <= ta_rate.slab2_upto_km: ta = round(billed_distance * float(ta_rate.slab2_rate), 2)
        else: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': True}
        return {'da': round(float(da), 2), 'ta': ta, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
    except TARate.DoesNotExist: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}


def _fill_missing_dates(master_report, employee):
    """Submit ke waqt pura month ensure karo — missing dates zero se fill karo, ya RECOVER karo."""
    import calendar
    from datetime import date
    m, y = master_report.month, master_report.year
    existing = set(master_report.daily_lines.values_list('date', flat=True))
    
    for d in range(1, calendar.monthrange(y, m)[1] + 1):
        l_date = date(y, m, d)
        if l_date not in existing:
            da, ta, dist, eff_cat, night_stay, is_slab3 = 0.00, 0.00, 0.00, 'HQ', False, False
            
            # 🌟 AUTO-RECONCILIATION LOGIC (Smart Recovery)
            ds_obj = DayStart.objects.filter(employee=employee, date=l_date).first()
            de_exists = DayEnd.objects.filter(employee=employee, date=l_date, is_closed=True).exists()
            
            # Agar us din kaam hua tha (Field Work, Meeting, Transit) aur day end bhi hua tha
            if ds_obj and de_exists and ds_obj.work_type in ['Field Work', 'Transit', 'Meeting']:
                exp_data = calculate_missing_expense(employee, ds_obj)
                da = exp_data['da']
                ta = exp_data['ta']
                dist = exp_data['distance']
                eff_cat = exp_data['territory_category']
                night_stay = exp_data['night_stay']
                is_slab3 = exp_data['is_slab3']

            DailyExpense.objects.create(
                employee=employee, date=l_date,
                monthly_report=master_report,
                da_amount=da,
                ta_amount=ta,
                misc_amount=0.00,
                distance_km=dist,
                territory_category=eff_cat,
                night_stay=night_stay,
                is_slab3=is_slab3
            )


@employee_required
def review_expense_view(request, employee, exp_id):
    manager    = employee
    exp_report = get_object_or_404(MonthlyExpenseReport, id=exp_id)

    # Authorization check
    if exp_report.employee not in get_full_team_employees(manager) and manager.designation != 'NSM':
        return redirect('manager_approvals')

    daily_expenses = exp_report.daily_lines.all().order_by('date')

    for de in daily_expenses:
        de.day_claimed = float((de.ta_amount or 0) + (de.da_amount or 0) + (de.misc_amount or 0))

    total_claimed  = sum(de.day_claimed for de in daily_expenses)
    total_approved = sum(
        float(de.approved_ta   if de.approved_ta   is not None else de.ta_amount) +
        float(de.approved_da   if de.approved_da   is not None else de.da_amount) +
        float(de.approved_misc if de.approved_misc is not None else de.misc_amount)
        for de in daily_expenses
    )

    if request.method == "POST":
        action = request.POST.get('action')
        remark = request.POST.get('manager_remark', '').strip()

        if action == 'Reject':
            exp_report.status         = 'Rejected'
            exp_report.manager_remark = remark
            exp_report.save()
            return redirect('manager_approvals')

        elif action == 'Approve':
            is_changed = False
            for de in daily_expenses:
                try:
                    new_ta   = float(request.POST.get(f'app_ta_{de.id}',   de.approved_ta   if de.approved_ta   is not None else de.ta_amount))
                    new_da   = float(request.POST.get(f'app_da_{de.id}',   de.approved_da   if de.approved_da   is not None else de.da_amount))
                    new_misc = float(request.POST.get(f'app_misc_{de.id}', de.approved_misc if de.approved_misc is not None else de.misc_amount))
                    de.approved_ta, de.approved_da, de.approved_misc = new_ta, new_da, new_misc
                    de.save()
                    if float(de.ta_amount) != new_ta or float(de.da_amount) != new_da or float(de.misc_amount) != new_misc:
                        is_changed = True
                except ValueError:
                    pass
            exp_report.status         = 'Approved'
            exp_report.manager_remark = remark
            exp_report.is_modified    = is_changed
            exp_report.save()
            return redirect('manager_approvals')

    return render(request, 'review_expense.html', {
        'exp_report':     exp_report,
        'daily_expenses': daily_expenses,
        'total_claimed':  round(total_claimed, 2),
        'total_approved': round(total_approved, 2),
    })
