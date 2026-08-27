"""
SFA/api/core_misc.py
=====================
Notices, compliance alerts, location, notifications, messages,
vacancy list, my-requests tracker, MTP (tour plan) handlers.
(core.py se split kiya gaya — 1000+ line limit ke wajah se)
"""

import calendar
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Q

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from SFA.models import (
    Employee, Doctor, Chemist, Route, Territory, DailyTourPlan,
    DayStart, DayEnd, DailyDCR, DCRVisit, DCRProductDetail, Product, MRInventory,
    DailyDCRStatus, LeaveApplication, Holiday,
    MonthlyTourProgram, MonthlyExpenseReport, PartyWiseSaleReport,
    MonthlyTargetMaster, FreeQtyClaimMaster, GiftCampaignPlan,
    SystemSetting, CompanyNotice, DailyExpense, DARate, TARate, HQDistance,
    SystemNotification, DirectMessage, DoctorEditRequest, ChemistEditRequest, LeaveBalance
)

from SFA.services.team import (
    get_full_team_employees,
    get_team_territory_ids,
    get_team_route_ids,
)
from SFA.views.core import sync_dcr_calendar, get_open_day, _normalize_status

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_notices(request):
    employee = request.user.employee  # 🌟 FIX: pehle employee fetch hi nahi hota tha
    notices = CompanyNotice.objects.filter(company=employee.company, is_active=True).order_by('-created_at')[:20]  # 🌟 FIX: company-scoped
    return Response([{'id': n.id, 'title': n.title, 'body': n.body, 'date': str(n.created_at.date()) if n.created_at else None} for n in notices])

# ==============================================================================
# 🔧 PRIVATE HELPERS
# ==============================================================================

# ==============================================================================
# 🔧 PRIVATE HELPERS
# ==============================================================================

def _get_compliance_alerts(employee, today, setting):
    alerts = []
    is_new_joiner = employee.joining_date and (today - employee.joining_date).days <= 7
    curr_month, curr_year = today.month, today.year
    next_month, next_year = (1, curr_year + 1) if curr_month == 12 else (curr_month + 1, curr_year)
    prev_month, prev_year = (12, curr_year - 1) if curr_month == 1 else (curr_month - 1, curr_year)
    worked_last_month = DayStart.objects.filter(employee=employee, date__month=prev_month, date__year=prev_year).exists()

    if employee.designation == 'MR':
        if not is_new_joiner and not MonthlyTourProgram.objects.filter(employee=employee, month=curr_month, year=curr_year, status__in=['Pending', 'Approved']).exists():
            alerts.append(f"Tour Plan for current month ({curr_month}/{curr_year}) is missing.")

        deadline = setting.mtp_approval_deadline_day if setting else 25
        if not is_new_joiner and today.day > deadline and not MonthlyTourProgram.objects.filter(employee=employee, month=next_month, year=next_year, status__in=['Pending', 'Approved']).exists():
            alerts.append(f"Tour Plan for next month ({next_month}/{next_year}) is not submitted yet.")

        if worked_last_month:
            exp_deadline = setting.expense_submit_deadline_day if setting else 4
            if today.day > exp_deadline and not MonthlyExpenseReport.objects.filter(employee=employee, month=prev_month, year=prev_year, status__in=['Pending', 'Approved']).exists():
                alerts.append(f"Expense Report for previous month ({prev_month}/{prev_year}) is pending.")
    else:
        team_employees = get_full_team_employees(employee)
        subordinate_ids = team_employees.exclude(id=employee.id).values_list('id', flat=True)
        pending_items = []

        if MonthlyTourProgram.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Tour Plans')
        if MonthlyExpenseReport.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Expenses')
        if LeaveApplication.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Leaves')

        if pending_items:
            alerts.append(f"Pending team approvals required: {', '.join(pending_items)}")

    return alerts

def _get_compliance_block(employee, today, setting):
    if not setting: return None
    is_new_joiner = employee.joining_date and (today - employee.joining_date).days <= 7
    curr_month, curr_year = today.month, today.year

    if employee.designation == 'MR':
        if not is_new_joiner and setting.without_tourplan_dcr_block:
            if not MonthlyTourProgram.objects.filter(employee=employee, month=curr_month, year=curr_year, status__in=['Pending', 'Approved']).exists():
                return f"Tour Plan for the current month is missing. Please submit your MTP to proceed."
    else:
        if setting.manager_pending_approval_block:
            team_employees = get_full_team_employees(employee)
            subordinate_ids = team_employees.exclude(id=employee.id).values_list('id', flat=True)
            pending = []
            if MonthlyTourProgram.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending.append('Tour Plans')
            if MonthlyExpenseReport.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending.append('Expenses')
            if pending:
                return f"Pending team approvals ({', '.join(pending)}). Please approve them first to unlock your DCR."
    return None

# ==============================================================================
# 📍 UPDATE LOCATION
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_update_location(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    role = request.data.get('role')
    target_id = request.data.get('target_id')
    lat = request.data.get('latitude')
    lng = request.data.get('longitude')

    if role == 'doctor':
        target = get_object_or_404(Doctor, id=target_id, company=employee.company)
    elif role == 'chemist':
        target = get_object_or_404(Chemist, id=target_id, company=employee.company)
    else:
        return Response({'success': False, 'error': 'Invalid role provided.'}, status=400)

    setting = SystemSetting.objects.filter(company=employee.company).first()
    is_global_open = setting.allow_location_capture if setting else True

    if target.latitude and not is_global_open:
        # 🌟 FIX: Professional English
        return Response({'success': False, 'error': f'Location for {target.name} is already locked. Please contact the administrator.'}, status=403)

    if lat is not None and lng is not None:
        # 🌟 FIX: Float to String for PostgreSQL DecimalField
        target.latitude = str(lat)
        target.longitude = str(lng)
        target.save()
        # 🌟 FIX: Professional English
        return Response({'success': True, 'message': f'Location for {target.name} has been saved successfully!'})
        
    # 🌟 FIX: Professional English
    return Response({'success': False, 'error': 'GPS coordinates are missing.'}, status=400)
# ==============================================================================
# 🔔 NOTIFICATIONS
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_notifications(request):
    employee = request.user.employee
    notifications = SystemNotification.objects.filter(employee=employee).order_by('-created_at')
    
    data = []
    for n in notifications:
        data.append({'id': n.id, 'title': n.title, 'message': n.message, 'is_read': n.is_read, 'date': n.created_at.strftime('%d %b %Y, %I:%M %p')})
    
    notifications.filter(is_read=False).update(is_read=True)
    return Response({'success': True, 'notifications': data})
# 🌟 NAYA: Unread Notifications Count (Read mark nahi karega)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_unread_notifications_count(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)
        
    unread_notifs = SystemNotification.objects.filter(employee=employee, is_read=False)
    
    # Notice wale notifications ka title '📢 ' se shuru hota hai (notice_board_view se)
    unread_notices = unread_notifs.filter(title__startswith='📢').count()
    # Baaki sab alerts hain (Approvals, Leaves, etc.)
    unread_alerts = unread_notifs.exclude(title__startswith='📢').count()
    
    return Response({
        'unread_alerts': unread_alerts,
        'unread_notices': unread_notices
    })
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_messages(request):
    employee = request.user.employee

    if request.method == 'POST':
        receiver_id = request.data.get('receiver_id')
        body = request.data.get('message')
        
        if not receiver_id or not body:
            return Response({'success': False, 'error': 'Receiver ya message missing hai.'}, status=400)
            
        receiver_emp = get_object_or_404(Employee, id=receiver_id, company=employee.company)        
        DirectMessage.objects.create(sender=employee, receiver=receiver_emp, message=body)
        return Response({'success': True, 'message': f'Message sent to {receiver_emp.name}!'})

    # 🚀 OPTIMIZATION: select_related lagaya taaki N+1 queries fire na hon
    received = DirectMessage.objects.filter(receiver=employee).select_related('sender').order_by('-created_at')
    sent = DirectMessage.objects.filter(sender=employee).select_related('receiver').order_by('-created_at')
    
    received.filter(is_read=False).update(is_read=True)
    
    allowed_ids = []
    if employee.designation in ['Admin', 'System Administrator']:
        contacts = Employee.objects.filter(company=employee.company).exclude(id=employee.id).order_by('-designation', 'name')
    else:
        allowed_ids = list(get_full_team_employees(employee).values_list('id', flat=True))
        curr = employee.manager
        while curr:
            if curr.is_active: allowed_ids.append(curr.id)
            curr = curr.manager
        admin_ids = list(Employee.objects.filter(company=employee.company, designation__in=['Admin', 'System Administrator']).values_list('id', flat=True))
        allowed_ids.extend(admin_ids)
        contacts = Employee.objects.filter(id__in=set(allowed_ids)).exclude(id=employee.id).order_by('-designation', 'name')

    return Response({
        'success': True,
        'contacts': [{'id': c.id, 'name': c.name, 'designation': c.designation} for c in contacts],
        'inbox': [{'id': m.id, 'sender': m.sender.name, 'message': m.message, 'date': m.created_at.strftime('%d %b, %I:%M %p')} for m in received],
        'sentbox': [{'id': m.id, 'receiver': m.receiver.name, 'message': m.message, 'date': m.created_at.strftime('%d %b, %I:%M %p')} for m in sent]
    })

# ==============================================================================
# 📝 EDIT VISIT
# ==============================================================================
# ==============================================================================
# 📝 EDIT VISIT
# ==============================================================================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_vacancy_list(request):
    employee = request.user.employee
    vacancies = get_full_team_employees(employee).filter(is_placeholder=True).select_related('headquarter', 'manager').order_by('headquarter__name', 'designation')

    data = []
    for v in vacancies:
        data.append({
            'id': v.id, 'name': v.name, 'hq': v.headquarter.name if v.headquarter else 'No HQ',
            'designation': v.designation, 'doc_count': Doctor.objects.filter(allocated_to=v).count(),
            'chem_count': Chemist.objects.filter(allocated_to=v).count(), 'team_count': Employee.objects.filter(manager=v).count(),
        })

    return Response({'success': True, 'vacancies': data})

# ==============================================================================
# 📋 MY REQUESTS
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_my_requests(request):
    employee = request.user.employee
    req_list = []

    for leave in LeaveApplication.objects.filter(employee=employee).order_by('-applied_on')[:20]:
        req_list.append({'type': 'Leave', 'date': leave.applied_on, 'detail': f"{leave.get_leave_type_display()} ({leave.start_date} to {leave.end_date})", 'status': _normalize_status(leave.status), 'remark': leave.manager_remark})

    for claim in FreeQtyClaimMaster.objects.filter(employee=employee).order_by('-id')[:20]:
        req_list.append({'type': 'Free Claim', 'date': claim.created_at if hasattr(claim, 'created_at') else None, 'detail': f"{calendar.month_name[claim.month]} {claim.year}", 'status': _normalize_status(claim.status), 'remark': claim.manager_remark})

    for mtp in MonthlyTourProgram.objects.filter(employee=employee).order_by('-created_at')[:20]:
        req_list.append({'type': 'Tour Plan (MTP)', 'date': mtp.created_at, 'detail': f"{calendar.month_name[mtp.month]} {mtp.year}", 'status': _normalize_status(mtp.status), 'remark': mtp.manager_remark})

    if employee.headquarter_id:
        for target in MonthlyTargetMaster.objects.filter(territory_id=employee.headquarter_id).order_by('-id')[:20]:
            req_list.append({'type': 'Target', 'date': None, 'detail': f"{calendar.month_name[target.month]} {target.year}", 'status': _normalize_status(target.status), 'remark': target.manager_remark})

    req_list.sort(key=lambda r: r['date'] or timezone.now() - timedelta(days=36500), reverse=True)

    for r in req_list:
        if r['date']: r['date'] = r['date'].strftime('%d %b %Y')

    return Response({'success': True, 'requests': req_list})



import json
import calendar
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from SFA.models import (
    Employee, Route, MonthlyTourProgram, DailyTourPlan, 
    LeaveApplication, Holiday, SystemSetting
)
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.http import JsonResponse
import json
import calendar
from datetime import date, datetime, timedelta
from SFA.models import (
    Employee, Route, MonthlyTourProgram, DailyTourPlan, 
    LeaveApplication, Holiday, SystemSetting
)
from SFA.views.auth import get_full_team_employees, get_team_route_ids

# 🌟 FIX: Token Auth aur api_view lagaya gaya hai
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_mtp(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Authentication failed'}, status=401)

    if request.method == "GET":
        return handle_get_mtp(employee)
    elif request.method == "POST":
        return handle_post_mtp(employee, request)
    else:
        return Response({'error': 'Invalid request'}, status=405)


def handle_get_mtp(employee):
    """Flutter ko MTP ka initial data (Calendar, Routes, Leaves) bhejne ke liye"""
    today = timezone.localdate()
    current_year = today.year
    curr_month = today.month
    next_month, next_year = (1, current_year + 1) if curr_month == 12 else (curr_month + 1, current_year)

    # Allowed Months Logic
    is_new_joiner = employee.joining_date and (today - employee.joining_date).days <= 7
    setting = SystemSetting.objects.filter(company=employee.company).first()
    allow_current_month = setting.allow_current_month_mtp if setting else False

    allowed_months = [
        {'month': next_month, 'year': next_year, 'name': calendar.month_name[next_month], 'label': f"{calendar.month_name[next_month]} {next_year}"}
    ]
    if is_new_joiner or allow_current_month:
        allowed_months.insert(0, {'month': curr_month, 'year': current_year, 'name': calendar.month_name[curr_month], 'label': f"{calendar.month_name[curr_month]} {current_year}"})

    # 🌟 FIX: Routes Fetch mein Company filter lagaya
    team_employees = get_full_team_employees(employee)
    all_terr_ids = list(team_employees.exclude(headquarter__isnull=True).values_list('headquarter_id', flat=True))
    routes = Route.objects.filter(territory_id__in=all_terr_ids, company=employee.company, status='Approved').select_related('territory').order_by('category', 'name')
    routes_data = [{'id': r.id, 'name': r.name, 'category': r.category, 'territory': r.territory.name} for r in routes]

    # Existing Drafts Fetch
    draft_mtps = MonthlyTourProgram.objects.filter(employee=employee, status__in=['Draft', 'Rejected']).order_by('-year', '-month')
    
    mtp_calendar_data = []
    for mtp in draft_mtps:
        # Leaves Logic
        approved_leaves = LeaveApplication.objects.filter(
            employee=employee, status='Approved',
            start_date__lte=date(mtp.year, mtp.month, calendar.monthrange(mtp.year, mtp.month)[1]),
            end_date__gte=date(mtp.year, mtp.month, 1)
        )
        leave_dates = {}
        for l in approved_leaves:
            delta = l.end_date - l.start_date
            for i in range(delta.days + 1):
                d = l.start_date + timedelta(days=i)
                if d.month == mtp.month and d.year == mtp.year:
                    leave_dates[d.day] = l.leave_type

        # Holidays Logic
        rbm_emp = None
        curr = employee
        while curr:
            if curr.designation == 'RBM': rbm_emp = curr; break
            curr = curr.manager
            
        holiday_creators = list(Employee.objects.filter(designation='Admin', company=employee.company).values_list('id', flat=True))
        if rbm_emp: holiday_creators.append(rbm_emp.id)
        
        holidays = Holiday.objects.filter(proposed_by_id__in=holiday_creators, status='Approved', date__month=mtp.month, date__year=mtp.year)
        holiday_dates = {h.date.day: h.name for h in holidays}

        existing_plans = {p.date.day: p.route_id for p in DailyTourPlan.objects.filter(mtp=mtp)}

        # DOJ Logic
        start_day = 1
        if employee.joining_date:
            mtp_val = mtp.year * 12 + mtp.month
            join_val = employee.joining_date.year * 12 + employee.joining_date.month
            if mtp_val == join_val: start_day = employee.joining_date.day
            elif mtp_val < join_val: start_day = 32 

        days_list = []
        num_days = calendar.monthrange(mtp.year, mtp.month)[1]
        for day in range(start_day, num_days + 1):
            curr_date = date(mtp.year, mtp.month, day)
            is_sunday = curr_date.weekday() == 6
            is_leave = day in leave_dates
            is_holiday = day in holiday_dates

            status_text = ""
            if is_leave: status_text = f"🏖️ On Leave ({leave_dates[day]})"
            elif is_holiday: status_text = f"⛱️ {holiday_dates[day]}"
            elif is_sunday: status_text = "🔴 Sunday"

            days_list.append({
                'day': day,
                'date_str': curr_date.strftime("%d %b, %a"),
                'is_locked': is_leave or is_holiday or is_sunday,
                'status_text': status_text,
                'selected_route_id': existing_plans.get(day)
            })

        if days_list:
            mtp_calendar_data.append({
                'mtp_id': mtp.id,
                'month': mtp.month,
                'year': mtp.year,
                'status': mtp.status,
                'days': days_list
            })

    return Response({
        'allowed_months': allowed_months,
        'routes': routes_data,
        'drafts': mtp_calendar_data
    })


def handle_post_mtp(employee, request):
    """Flutter se MTP Create, Save ya Submit karne ke liye"""
    # 🌟 FIX: request.body se JSON parse karna (Token auth ke sath)
    try:
        data = json.loads(request.body)
    except:
        return Response({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')

    if action == 'create_mtp':
        m = int(data.get('month'))
        y = int(data.get('year'))
        today = timezone.localdate()
        curr_month, current_year = today.month, today.year
        next_month, next_year = (1, current_year + 1) if curr_month == 12 else (curr_month + 1, current_year)
        
        is_new_joiner = employee.joining_date and (today - employee.joining_date).days <= 7
        setting = SystemSetting.objects.filter(company=employee.company).first()
        allowed = [{'month': next_month, 'year': next_year}]
        if is_new_joiner or (setting and setting.allow_current_month_mtp):
            allowed.append({'month': curr_month, 'year': current_year})

        is_allowed = any(am['month'] == m and am['year'] == y for am in allowed)
        if not is_allowed:
            return Response({'error': '⚠️ Kripya sirf allowed mahine ka hi Tour Plan banayein.'}, status=403)

        if employee.joining_date:
            mtp_val = y * 12 + m
            join_val = employee.joining_date.year * 12 + employee.joining_date.month
            if mtp_val < join_val:
                return Response({'error': f'❌ Aap apni joining date se pehle ka Tour Plan nahi bana sakte!'}, status=403)

        if not MonthlyTourProgram.objects.filter(employee=employee, month=m, year=y).exists():
            mtp = MonthlyTourProgram.objects.create(employee=employee, month=m, year=y, status='Draft')
            return Response({'success': True, 'message': 'Draft created!', 'mtp_id': mtp.id})
        else:
            return Response({'error': 'Is mahine ka plan pehle se maujood hai!'}, status=400)

    elif action in ['save_plan', 'submit_plan']:
        mtp_id = data.get('mtp_id')
        plans_data = data.get('plans') # Flutter se aayega: {"1": 5, "2": null, "3": 12} (Day: RouteID)
        
        try:
            mtp = MonthlyTourProgram.objects.get(id=mtp_id, employee=employee)
        except MonthlyTourProgram.DoesNotExist:
            return Response({'error': 'MTP not found'}, status=404)

        DailyTourPlan.objects.filter(mtp=mtp).delete()

        start_day = 1
        if employee.joining_date:
            mtp_val = mtp.year * 12 + mtp.month
            join_val = employee.joining_date.year * 12 + employee.joining_date.month
            if mtp_val == join_val: start_day = employee.joining_date.day
            elif mtp_val < join_val: start_day = 32 

        num_days = calendar.monthrange(mtp.year, mtp.month)[1]
        for day in range(start_day, num_days + 1):
            route_id = plans_data.get(str(day)) if plans_data else None
            if route_id:
                curr_date = date(mtp.year, mtp.month, day)
                if curr_date.weekday() == 6: continue # Sunday Block
                DailyTourPlan.objects.create(mtp=mtp, date=curr_date, route_id=route_id)
                
        if action == 'submit_plan':
            mtp.status = 'Pending'
            mtp.save()
            return Response({'success': True, 'message': f'🚀 MTP for {calendar.month_name[mtp.month]} submitted to Manager!'})
        else:
            return Response({'success': True, 'message': '💾 Draft saved successfully!'})

    return Response({'error': 'Invalid action provided'}, status=400)
# ==============================================================================
# 📅 CALENDAR EVENTS API
# ==============================================================================

import calendar
from datetime import date, timedelta
from collections import defaultdict

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_calendar_events(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    # Month aur Year query params se lo (default current month/year)
    today = timezone.localdate()
    year = int(request.query_params.get('year', today.year))
    month = int(request.query_params.get('month', today.month))

    # 1. Hierarchy Logic: MR ko khud ka, Manager ko team ka
    if employee.designation == 'MR':
        team_employees = [employee]
    else:
        team_employees = list(get_full_team_employees(employee))
        if employee not in team_employees:
            team_employees.append(employee)
            
    team_ids = [e.id for e in team_employees]

    events_map = defaultdict(list)

    # 2. Holidays Scan
    holidays = Holiday.objects.filter(company=employee.company, date__year=year, date__month=month, status='Approved')
    for h in holidays:
        events_map[h.date.isoformat()].append(f"🏖️ {h.name}")

    # 3. Leaves Scan (Date range check)
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])
    leaves = LeaveApplication.objects.filter(
        employee_id__in=team_ids, 
        start_date__lte=end_date, 
        end_date__gte=start_date
    ).exclude(status='Rejected')
    
    for leave in leaves:
        current = max(leave.start_date, start_date)
        end = min(leave.end_date, end_date)
        while current <= end:
            events_map[current.isoformat()].append(f"🏖️ {leave.employee.name} on Leave")
            current += timedelta(days=1)

    # 4. Employee Birthdays & Anniversaries Scan
    for emp in team_employees:
        if emp.dob and emp.dob.month == month:
            try:
                dt_str = date(year, month, emp.dob.day).isoformat()
                events_map[dt_str].append(f"🎂 {emp.name} Birthday")
            except ValueError: pass # Skip invalid dates like Feb 29
                
        if emp.anniversary and emp.anniversary.month == month:
            try:
                dt_str = date(year, month, emp.anniversary.day).isoformat()
                events_map[dt_str].append(f"💍 {emp.name} Anniversary")
            except ValueError: pass

    # 🚀 OPTIMIZATION: Python RAM loop ki jagah Database (SQL) level par __month filtering lagayi
    
    # 5. Doctor Birthdays & Anniversaries Scan
    doctors_bday = Doctor.objects.filter(allocated_to_id__in=team_ids, dob__month=month)
    for doc in doctors_bday:
        try:
            dt_str = date(year, month, doc.dob.day).isoformat()
            events_map[dt_str].append(f"🎂 Dr. {doc.name} Birthday")
        except ValueError: pass
            
    doctors_anniv = Doctor.objects.filter(allocated_to_id__in=team_ids, dom__month=month)
    for doc in doctors_anniv:
        try:
            dt_str = date(year, month, doc.dom.day).isoformat()
            events_map[dt_str].append(f"💍 Dr. {doc.name} Anniversary")
        except ValueError: pass

    # 6. Chemist Owner Birthdays Scan
    chemists_bday = Chemist.objects.filter(allocated_to_id__in=team_ids, owner_dob__month=month)
    for chem in chemists_bday:
        try:
            dt_str = date(year, month, chem.owner_dob.day).isoformat()
            events_map[dt_str].append(f"🎂 {chem.name} (Owner) Birthday")
        except ValueError: pass

    return Response(dict(events_map))
    