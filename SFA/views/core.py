import sys
import calendar
from io import BytesIO
from django.http import JsonResponse
from SFA.models import MRInventory, DoctorROILedger
from SFA.models import SystemSetting, DailyDCRStatus, Holiday, LeaveApplication, MonthlyTargetMaster, FreeQtyClaimMaster
from datetime import timedelta
from PIL import Image
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import InMemoryUploadedFile
import django.core.files.locks as locks
from SFA.models import Doctor, Chemist, SystemSetting
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from SFA.models import GiftCampaignPlan
from SFA.models import DoctorEditRequest, ChemistEditRequest
from SFA.models import (
    Employee, Territory, Route, DayStart, DayEnd, DailyTourPlan, 
    LeaveApplication, MonthlyTourProgram, MonthlyExpenseReport, 
    PartyWiseSaleReport, FreeQtyClaimMaster, MonthlyTargetMaster, 
    PromoDispatch, Holiday
)
from SFA.models import InternalMessage, MessageAttachment, Employee
from django.shortcuts import get_object_or_404
# 🌟 NAYA: Yahan aakhir mein 'LeaveApplication' add kiya gaya hai
from SFA.models import (
    Employee, Doctor, Chemist, DayEnd, DayStart, Product, Route,
    DailyDCR, DCRVisit, DCRProductDetail, DailyTourPlan, Territory,
    MonthlyExpenseReport, DailyExpense, DARate, TARate, LeaveApplication, CompanyNotice
)
from .auth import get_full_team_employees, get_team_territory_ids, get_team_route_ids, get_team_tree
from SFA.decorators import employee_required
import os
import json
from django.conf import settings
from SFA.models import SystemNotification
from SFA.models import Doctor, Chemist

@employee_required
def update_location_view(request, employee, role, target_id):
    if role == 'doctor':
        target = get_object_or_404(Doctor, id=target_id)
    elif role == 'chemist':
        target = get_object_or_404(Chemist, id=target_id)
    else:
        return redirect('mr_dashboard')

    # 🌟 FIX: employee_id ko GET (page load) ya POST (form submit) dono se le lo,
    # taaki redirect ke baad sahi tab + employee wapas mile
    emp_id = request.POST.get('employee_id') or request.GET.get('employee_id', '')
    redirect_url = f"/reports/network/?employee_id={emp_id}&tab={role}"

    # 🛑 SMART SECURITY LOGIC
    setting = SystemSetting.objects.filter(company=employee.company).first()
    is_global_open = setting.allow_location_capture if setting else True

    # Agar location pehle se set hai AUR Admin ka switch OFF hai, toh block kar do!
    if target.latitude and not is_global_open:
        messages.error(request, f"⚠️ {target.name} ki location pehle se lock hai. Update karne ke liye Admin se sampark karein.")
        return redirect(redirect_url)

    if request.method == "POST":
        lat = request.POST.get('latitude')
        lng = request.POST.get('longitude')
        
        if lat and lng:
            target.latitude = lat
            target.longitude = lng
            target.save()
            messages.success(request, f"📍 {target.name} ki exact location successfully save ho gayi!")
        else:
            messages.error(request, "⚠️ GPS fetch nahi ho paya. Kripya apne phone ki Location ON karein.")
            
        return redirect(redirect_url)

    return render(request, 'update_location.html', {'target': target, 'role': role, 'employee_id': emp_id})


# ==============================================================================
# 🌟 PYDROID / ANDROID FILE UPLOAD FIX
# ==============================================================================
def dummy_lock(fd, flags): return True
def dummy_unlock(fd): return True
locks.lock = dummy_lock
locks.unlock = dummy_unlock

# ==============================================================================
# 📸 IMAGE COMPRESSION TOOL (File size 10MB -> 150KB)
# ==============================================================================
def compress_photo(uploaded_file):
    if not uploaded_file: return None
    try:
        img = Image.open(uploaded_file)
        if img.mode != 'RGB': img = img.convert('RGB')
        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
        output = BytesIO()
        img.save(output, format='JPEG', quality=60)
        output.seek(0)
        return InMemoryUploadedFile(output, 'ImageField', f"{uploaded_file.name.split('.')[0]}.jpg", 'image/jpeg', sys.getsizeof(output), None)
    except Exception:
        return uploaded_file

def sync_dcr_calendar(employee):
    """Bina Cron Job ke har baar Calendar Sync aur Auto-Block karega"""
    today = timezone.localdate()
    setting = SystemSetting.objects.filter(company=employee.company).first()
    lock_days = setting.dcr_lock_days if setting else 3

    # 1. Calendar auto-fill — joining_date se pehle ka kabhi nahi banega (max 15 din peeche)
    start_date = max(employee.joining_date, today - timedelta(days=60))
    d = start_date
    while d <= today:
        status_obj, created = DailyDCRStatus.objects.get_or_create(employee=employee, date=d)

        if created:
            # Agar Sunday hai ya Holiday hai toh default band (False) rakho
            if d.weekday() == 6:  # 6 means Sunday
                status_obj.day_type = 'Sunday'
                status_obj.is_open = False
            elif Holiday.objects.filter(company=employee.company, date=d, status='Approved').exists():  # 🌟 FIX: company-scoped
                status_obj.day_type = 'Holiday'
                status_obj.is_open = False
            elif LeaveApplication.objects.filter(employee=employee, status='Approved', start_date__lte=d, end_date__gte=d).exists():
                status_obj.day_type = 'Leave'
                status_obj.is_open = False
            status_obj.save()
        d += timedelta(days=1)

    # 2. EXPIRED ADMIN-UNLOCK ko wapas reset karo (1-din ki validity khatam ho gayi)
    #    (unlocked_until__isnull=True bhi pakdega — purane migration-se-pehle ke unlock records)
    DailyDCRStatus.objects.filter(
        employee=employee, is_admin_unlocked=True
    ).filter(
        Q(unlocked_until__lt=today) | Q(unlocked_until__isnull=True)
    ).update(is_admin_unlocked=False, unlocked_until=None)

    # 3. THE AUTO-BLOCKER (lock_days se purani khuli dates ko band karna)
    cutoff_date = today - timedelta(days=lock_days)
    DailyDCRStatus.objects.filter(
        employee=employee, 
        date__lt=cutoff_date, 
        is_open=True, 
        is_admin_unlocked=False # Admin override ko nahi chhuiga
    ).update(is_open=False)


def get_open_day(employee):
    """
    Employee ka abhi tak 'open' (DayEnd na hua) DayStart dhoondta hai.
    🌟 SAFETY CHECK: Agar wo purani date lock ho chuki hai (DailyDCRStatus
    ke hisaab se) YA employee ki joining_date se pehle ki hai, to use
    'stuck/abandoned' maan kar return karo — taaki employee hamesha usi
    ek purani date me hamesha ke liye na fas jaaye.
    Returns: (open_day, stuck_day) — kisi bhi waqt sirf ek hi non-None hoga.
    """
    candidate = DayStart.objects.filter(employee=employee).exclude(
        date__in=DayEnd.objects.filter(employee=employee, is_closed=True).values_list('date', flat=True)
    ).order_by('date').first()

    if not candidate:
        return None, None

    status = DailyDCRStatus.objects.filter(employee=employee, date=candidate.date).first()
    is_locked = status is not None and not status.is_open
    is_before_joining = candidate.date < employee.joining_date

    if is_locked or is_before_joining:
        return None, candidate

    return candidate, None

@employee_required
def mr_dashboard_view(request, employee):
    sync_dcr_calendar(employee)
    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        messages.error(request, f"🚫 {stuck_day.date.strftime('%d %b %Y')} ka ek purana Day Start band (DayEnd) nahi hua tha, aur ab wo date lock/joining-se-pehle ki ho gayi hai. Naya kaam shuru karne ke liye Admin ko ye din Django Admin se manually close karna hoga (DayEnd add karke).")

    # 🌟 REMOVED: Pehle yahan har dashboard-load par "Draft Expense" warning
    # dikhti thi — jo galat jagah thi (roz-roz, chahe Draft kitna bhi purana
    # ho). Ye warning ab sirf Expense Hub me hi dikhti hai, aur sirf TABHI
    # jab employee khud 'Save' button dabaye — jo asli relevant moment hai
    # (taaki Submit bhoolne wali real-life problem solve ho, bina Dashboard
    # ko roz-roz clutter kiye).

    open_day, stuck_day = get_open_day(employee)

    # 🌟 NAYA: Check karein ki kya koi purani date abhi bhi 'Open' aur 'Unsubmitted' hai
    oldest_pending_status = DailyDCRStatus.objects.filter(
        employee=employee, is_open=True, is_submitted=False
    ).order_by('date').first()

    # Priority 1: Jo din start ho chuka hai (par end nahi hua)
    if open_day:
        working_date = open_day.date
    # Priority 2: Jo din abhi start hona baaki hai (Admin ne khola ho ya regular pending ho)
    elif oldest_pending_status:
        working_date = oldest_pending_status.date
    # Priority 3: Default aaj ka din
    else:
        working_date = timezone.localdate()

    is_day_started = open_day is not None
    is_day_ended = DayEnd.objects.filter(employee=employee, date=working_date, is_closed=True).exists()
    tp = DailyTourPlan.objects.select_related('route').filter(mtp__employee=employee, date=working_date, mtp__status='Approved').first()

    if request.method == "POST" and "add_extra_route" in request.POST:
        new_route_id = request.POST.get('extra_route')
        if new_route_id and open_day and not is_day_ended: open_day.routes.add(new_route_id); messages.success(request, "Extra route add ho gaya!")
        return redirect('mr_dashboard')

    active_routes, available_routes, pending_doctors, visited_docs, pending_chemists, visited_chems = [], [], [], [], [], []
    today_samples, today_pob = 0, 0
    
    if is_day_started and open_day.work_type == 'Field Work':
        active_routes = open_day.routes.all()
        team_employees = get_full_team_employees(employee)
        my_all_route_ids = set(Route.objects.filter(territory_id__in=team_employees.exclude(headquarter__isnull=True).values_list('headquarter_id', flat=True)).values_list('id', flat=True))
        
        # 🌟 FIX: Sirf Approved ke routes fetch honge
        my_all_route_ids.update(Doctor.objects.filter(allocated_to__in=team_employees, status='Approved').values_list('route_id', flat=True))
        my_all_route_ids.update(Chemist.objects.filter(allocated_to__in=team_employees, status='Approved').values_list('route_id', flat=True))
        my_all_route_ids.discard(None)
        
        available_routes = Route.objects.filter(id__in=my_all_route_ids).exclude(id__in=[r.id for r in active_routes]) if my_all_route_ids else Route.objects.filter(company=employee.company).exclude(id__in=[r.id for r in active_routes])
        
        daily_dcr = DailyDCR.objects.prefetch_related('visits__doctor', 'visits__chemist').filter(employee=employee, date=working_date).first()
        visited_doc_ids, visited_chem_ids = set(), set()
        if daily_dcr:
            all_visits = list(daily_dcr.visits.all())
            visited_docs, visited_chems = [v for v in all_visits if v.doctor], [v for v in all_visits if v.chemist]
            visited_doc_ids, visited_chem_ids = {v.doctor_id for v in visited_docs}, {v.chemist_id for v in visited_chems}
            
            agg = DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).aggregate(s=Sum('sample_qty'))
            today_samples = agg['s'] or 0
            
            for d in DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).select_related('product'):
                price = float(d.product.price) if getattr(d.product, 'price', None) else 0.0
                today_pob += (d.order_qty or 0) * price

        # 🌟 FIX: Sirf Approved hi dashboard pe dikhenge
        pending_doctors = [d for d in Doctor.objects.select_related('route').filter(allocated_to__in=team_employees, route__in=active_routes, status='Approved') if d.id not in visited_doc_ids]
        pending_chemists = [c for c in Chemist.objects.select_related('route').filter(allocated_to__in=team_employees, route__in=active_routes, status='Approved') if c.id not in visited_chem_ids]

    return render(request, 'dashboard.html', {
        'employee': employee, 'today': working_date, 
        'active_routes': active_routes, 'available_routes': available_routes, 
        'pending_doctors': pending_doctors, 'visited_doctors': visited_docs, 
        'pending_chemists': pending_chemists, 'visited_chemists': visited_chems, 
        'is_day_started': is_day_started, 'is_day_ended': is_day_ended, 'tp': tp, 
        'company_notices': CompanyNotice.objects.filter(company=employee.company, is_active=True).order_by('-created_at')[:5],
        'today_dr_visits': len(visited_docs), 
        'today_chem_visits': len(visited_chems), 
        'today_samples': today_samples, 
        'today_pob': round(today_pob, 2),
        'open_day': open_day
    })


from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import datetime

from datetime import datetime, date
from django.utils import timezone
from django.shortcuts import render, redirect
from django.contrib import messages

# Ensure you have all these models imported at the top of your views.py:
# from SFA.models import DayStart, DayEnd, Employee, Territory, Route, DailyTourPlan, LeaveApplication, MonthlyTourProgram, MonthlyExpenseReport, PartyWiseSaleReport, FreeQtyClaimMaster, MonthlyTargetMaster, PromoDispatch, Holiday



@employee_required
def request_hub_view(request, employee): return render(request, 'request_hub.html')

@employee_required
def view_hub_view(request, employee):
    selected_emp = get_object_or_404(Employee, id=request.GET.get('employee_id', str(employee.id)))
    return render(request, 'view_hub.html', {'team_employees': get_full_team_employees(employee).order_by('-designation', 'name') if employee.designation != 'MR' else [employee], 'selected_emp_id': selected_emp.id, 'selected_employee_name': selected_emp.name, 'is_manager_view': employee.designation != 'MR'})


@employee_required
def calendar_view(request, employee):
    from collections import defaultdict

    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

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
        events_map[h.date.day].append(f"🏖️ {h.name}")

    # 3. Leaves Scan (Date range check)
    start_date = datetime(year, month, 1).date()
    end_date = datetime(year, month, calendar.monthrange(year, month)[1]).date()
    leaves = LeaveApplication.objects.filter(
        employee_id__in=team_ids, start_date__lte=end_date, end_date__gte=start_date
    ).exclude(status='Rejected')
    for leave in leaves:
        current = max(leave.start_date, start_date)
        end = min(leave.end_date, end_date)
        while current <= end:
            events_map[current.day].append(f"🏖️ {leave.employee.name} on Leave")
            current += timedelta(days=1)

    # 4. Employee Birthdays & Anniversaries Scan
    for emp in team_employees:
        if emp.dob and emp.dob.month == month:
            events_map[emp.dob.day].append(f"🎂 {emp.name} Birthday")
        if emp.anniversary and emp.anniversary.month == month:
            events_map[emp.anniversary.day].append(f"💍 {emp.name} Anniversary")

    # 5. Doctor Birthdays & Anniversaries Scan
    doctors = Doctor.objects.filter(allocated_to_id__in=team_ids)
    for doc in doctors:
        if doc.dob and doc.dob.month == month:
            events_map[doc.dob.day].append(f"🎂 Dr. {doc.name} Birthday")
        if doc.dom and doc.dom.month == month:
            events_map[doc.dom.day].append(f"💍 Dr. {doc.name} Anniversary")

    # 6. Chemist Owner Birthdays Scan
    chemists = Chemist.objects.filter(allocated_to_id__in=team_ids)
    for chem in chemists:
        if chem.owner_dob and chem.owner_dob.month == month:
            events_map[chem.owner_dob.day].append(f"🎂 {chem.name} (Owner) Birthday")

    # ── Build the month grid (Sunday-start, India convention) ──
    cal = calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_data = []
        for day in week:
            if day == 0:
                week_data.append(None)
            else:
                week_data.append({
                    'day': day,
                    'events': events_map.get(day, []),
                    'is_today': (day == today.day and month == today.month and year == today.year),
                })
        weeks.append(week_data)

    # ── Prev / Next month navigation ──
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    # ── Upcoming Alerts (Next 3 Days) ──
    upcoming_alerts = []
    for i in range(0, 4):
        d = today + timedelta(days=i)
        if d.month == month and d.year == year:
            evs = events_map.get(d.day, [])
            if evs:
                upcoming_alerts.append({'date': d, 'events': evs})

    context = {
        'weeks': weeks,
        'month_name': calendar.month_name[month],
        'year': year,
        'month': month,
        'prev_month': prev_month, 'prev_year': prev_year,
        'next_month': next_month, 'next_year': next_year,
        'upcoming_alerts': upcoming_alerts,
        'weekday_labels': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
    }
    return render(request, 'calendar.html', context)

@employee_required
def organogram_view(request, employee):
    from SFA.models import Employee
    nodes = []
    
    # 1. Upar ke Managers fetch karo
    managers = employee.get_my_managers(include_inactive=False)
    managers.reverse() # Taaki sabse bada boss sabse upar aaye
    for m in managers:
        nodes.append({
            'id': m.id,
            'name': m.name,
            'role': m.designation,
            'hq': m.headquarter.name if m.headquarter else 'N/A',
            'is_me': False,
            'is_vacant': False,
            'depth': 0,
            'padding': 0 # CSS margin ke liye
        })
        
    # 2. Khud ko add karo
    nodes.append({
        'id': employee.id,
        'name': f"{employee.name} (You)",
        'role': employee.designation,
        'hq': employee.headquarter.name if employee.headquarter else 'N/A',
        'is_me': True,
        'is_vacant': False,
        'depth': 0,
        'padding': 0
    })
    
    # 3. Neeche ki team fetch karo (Recursive)
    def get_subs(parent, depth):
        direct_reports = Employee.objects.filter(manager=parent).exclude(id=parent.id).order_by('name')
        for sub in direct_reports:
            # Sirf active ya vacant places dikhani hain
            if not sub.is_active and not sub.is_placeholder:
                continue
                
            is_vacant = sub.is_placeholder
            nodes.append({
                'id': sub.id,
                'name': 'Vacant Position' if is_vacant else sub.name,
                'role': sub.designation,
                'hq': sub.headquarter.name if sub.headquarter else 'N/A',
                'is_me': False,
                'is_vacant': is_vacant,
                'depth': depth,
                'padding': depth * 24 # UI indent ke liye 24px per depth
            })
            get_subs(sub, depth + 1)
            
    get_subs(employee, 1)
        
    return render(request, 'organogram.html', {'nodes': nodes})

def _normalize_status(raw_status):
    """
    🌟 HELPER: Har model ka status-naming alag hai (kuch 'Pending', kuch
    'Pending_Manager'/'Pending_Admin', kuch 'Draft'). My Requests me ek
    consistent 3-bucket dikhane ke liye normalize karte hain.
    """
    if raw_status in ('Approved',):
        return 'Approved'
    if raw_status in ('Rejected',):
        return 'Rejected'
    if raw_status in ('Draft',):
        return 'Draft'
    return 'Pending'  # Pending, Pending_Manager, Pending_RSM, Pending_ZSM, Pending_Admin, etc.


@employee_required
def my_requests_view(request, employee):
    """
    🌟 NAYA: "Maine kya-kya bheja, kiska kya status hai" — sabke liye
    (MR bhi, Manager bhi). 7 alag models se data combine karke ek single
    timeline banata hai, taaki Manager ko approve hone ka wait na karna
    pade pata karne ke liye ki uska khud ka kaam kaha tak pahuncha.

    Target (MonthlyTargetMaster) Employee se directly linked nahi hai
    (Territory-based hai) — isliye employee.headquarter se reverse-match
    karte hain.
    """
    requests_list = []

    for leave in LeaveApplication.objects.filter(employee=employee).order_by('-applied_on')[:50]:
        requests_list.append({
            'type': 'Leave', 'icon': '🏖️', 'date': leave.applied_on,
            'detail': f"{leave.get_leave_type_display()} ({leave.start_date} to {leave.end_date})",
            'status': _normalize_status(leave.status), 'remark': leave.manager_remark,
        })

    for claim in FreeQtyClaimMaster.objects.filter(employee=employee).order_by('-id')[:50]:
        requests_list.append({
            'type': 'Free Claim', 'icon': '🎁', 'date': None,
            'detail': f"{calendar.month_name[claim.month]} {claim.year}" + (f" — {claim.stockist.name}" if claim.stockist else ""),
            'status': _normalize_status(claim.status), 'remark': claim.manager_remark or claim.admin_remark,
        })

    for edit_req in DoctorEditRequest.objects.filter(employee=employee).order_by('-created_at')[:50]:
        requests_list.append({
            'type': 'Doctor Edit', 'icon': '🩺', 'date': edit_req.created_at,
            'detail': f"Dr. {edit_req.doctor.name} — naya naam/data request",
            'status': _normalize_status(edit_req.status), 'remark': None,
        })

    for edit_req in ChemistEditRequest.objects.filter(employee=employee).order_by('-created_at')[:50]:
        requests_list.append({
            'type': 'Chemist Edit', 'icon': '🧪', 'date': edit_req.created_at,
            'detail': f"{edit_req.chemist.name} — edit request",
            'status': _normalize_status(edit_req.status), 'remark': None,
        })

    for gift in GiftCampaignPlan.objects.filter(employee=employee).order_by('-id')[:50]:
        requests_list.append({
            'type': 'Gift Campaign', 'icon': '🎀', 'date': None,
            'detail': f"Dr. {gift.doctor.name} — {gift.item.name} ({calendar.month_name[gift.month]} {gift.year})",
            'status': _normalize_status(gift.status), 'remark': gift.manager_remark,
        })

    for mtp in MonthlyTourProgram.objects.filter(employee=employee).order_by('-created_at')[:50]:
        requests_list.append({
            'type': 'Tour Plan (MTP)', 'icon': '📅', 'date': mtp.created_at,
            'detail': f"{calendar.month_name[mtp.month]} {mtp.year}",
            'status': _normalize_status(mtp.status), 'remark': mtp.manager_remark,
        })

    # 🌟 Target: Territory-based hai, employee se directly linked nahi.
    # Employee ke khud ke headquarter se match karte hain (jo territory
    # uska apna HQ hai), taaki use pata chale uske territory ka target
    # approval kaha tak pahuncha.
    if employee.headquarter_id:
        for target in MonthlyTargetMaster.objects.filter(territory_id=employee.headquarter_id).order_by('-id')[:50]:
            requests_list.append({
                'type': 'Target', 'icon': '🎯', 'date': None,
                'detail': f"{employee.headquarter.name} — {calendar.month_name[target.month]} {target.year}",
                'status': _normalize_status(target.status), 'remark': target.manager_remark,
            })

    # 🌟 FIX: Holiday (proposed by RBM/ZBM/NSM, Admin approve karta hai) —
    # pehle missing tha, ab cover kiya.
    for holiday in Holiday.objects.filter(proposed_by=employee).order_by('-id')[:50]:
        requests_list.append({
            'type': 'Holiday Proposal', 'icon': '⛱️', 'date': None,
            'detail': f"{holiday.name} — {holiday.date}",
            'status': _normalize_status(holiday.status), 'remark': None,
        })

    # Sabse naya pehle (date None wale neeche, kyunki unka exact sort-key nahi)
    requests_list.sort(key=lambda r: r['date'] or timezone.now() - timedelta(days=36500), reverse=True)

    return render(request, 'my_requests.html', {'requests_list': requests_list})

@employee_required
def day_start_view(request, employee):
    # 🌟 CALENDAR SYNC (Always up-to-date)
    sync_dcr_calendar(employee)

    today = timezone.localdate()
    setting = SystemSetting.objects.filter(company=employee.company).first()

    # Sabse purana OPEN din dhoondho
    pending_days = DailyDCRStatus.objects.filter(
        employee=employee, is_open=True, is_submitted=False
    ).order_by('date')
    
    oldest_open = None
    for dcr in pending_days:
        # Check karo ki kya is din koi Leave ya Holiday approve ho chuki hai
        is_leave_day = LeaveApplication.objects.filter(
            employee=employee, status='Approved', start_date__lte=dcr.date, end_date__gte=dcr.date
        ).exists()
        is_holiday = Holiday.objects.filter(company=employee.company, date=dcr.date, status='Approved').exists()  # 🌟 FIX: company-scoped
        
        if is_leave_day or is_holiday or dcr.date.weekday() == 6:
            # Agar Leave/Holiday phas gaya hai, toh us din ko silently close (lock) kar do
            dcr.is_open = False
            dcr.day_type = 'Leave' if is_leave_day else ('Holiday' if is_holiday else 'Sunday')
            dcr.save()
        else:
            # Jo pehla asli working day milega, wahi oldest_open banega
            oldest_open = dcr
            break

    # Request se date nikalo (GET ya POST dono check karo)
    date_str = request.GET.get('date') or (request.POST.get('date') if request.method == 'POST' else None)
    
    if date_str:
        try: 
            working_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError: 
            working_date = today
    else:
        # 🔥 SMART FIX: Agar date select nahi ki hai (Dashboard se aaya hai), 
        # toh automatically sabse purani pending date ko 'working_date' bana do!
        working_date = oldest_open.date if oldest_open else today

    # =======================================================
    # 🛑 1. CHECK CALENDAR STATUS (Time-Driven Block)
    # =======================================================
    dcr_status = DailyDCRStatus.objects.filter(employee=employee, date=working_date).first()
    if dcr_status and not dcr_status.is_open:
        if dcr_status.is_submitted:
            messages.success(request, f"✅ {working_date.strftime('%d %b')} ka Day End already ho chuka hai (DCR submit ho gaya). Agar kuch pending purani dates hain to wo agli baar khud khulegi.")
        else:
            messages.error(request, f"🚫 DATE BLOCKED: {working_date.strftime('%d %b')} ka DCR lock ho chuka hai (Allowed limit cross ho gayi ya Sunday/Holiday hai). Kripya Admin se sampark karein.")
        return redirect('mr_dashboard')

    # 🔄 2. SEQUENTIAL CHECK (Pichla pending chhod kar aage nahi badh sakte)
    if oldest_open and working_date > oldest_open.date:
        messages.error(request, f"🚫 SEQUENCE BLOCKED: Aap dates skip nahi kar sakte. Pehle {oldest_open.date.strftime('%d %b')} ka DCR submit karein.")
        # Dashboard par fekne ke bajaye seedha usi date ke form par redirect kar do!
        return redirect(f'/start/?date={oldest_open.date}')

    # Leave Check (Safety net)
    is_on_leave = LeaveApplication.objects.filter(
        employee=employee, status='Approved', start_date__lte=working_date, end_date__gte=working_date
    ).exists()
    if is_on_leave:
        messages.error(request, f"🚫 Action Blocked: Aapki {working_date.strftime('%d %b')} ki chhutti (Leave) Approved hai! Aap Day Start nahi kar sakte.")
        return redirect('mr_dashboard')

    # =======================================================
    # 🚨 3. COMPLIANCE BLOCKS (Action-Driven Block)
    # =======================================================
    is_new_joiner = employee.joining_date and (today - employee.joining_date).days <= 7
    curr_month, curr_year = today.month, today.year
    next_month, next_year = (1, curr_year + 1) if curr_month == 12 else (curr_month + 1, curr_year)
    prev_month, prev_year = (12, curr_year - 1) if curr_month == 1 else (curr_month - 1, curr_year)
    worked_last_month = DayStart.objects.filter(employee=employee, date__month=prev_month, date__year=prev_year).exists()

    alerts = []

    # 🟢 A. STRICT RULES FOR MR
    if employee.designation == 'MR':
        # 1. CURRENT MONTH MTP RULE
        if not is_new_joiner and not MonthlyTourProgram.objects.filter(employee=employee, month=curr_month, year=curr_year, status__in=['Pending', 'Approved']).exists():
            msg = f"Aapka is mahine ({curr_month}/{curr_year}) ka Tour Plan system mein nahi hai (ya Reject ho gaya hai)!"
            if setting and setting.without_tourplan_dcr_block:
                messages.error(request, f"🚫 ACTION BLOCKED: {msg} Pehle is mahine ka MTP banakar Manager ko submit karein.")
                return redirect('mr_dashboard')
            alerts.append(msg)
            
        # 2. NEXT MONTH MTP RULE
        if not is_new_joiner and today.day > (setting.mtp_approval_deadline_day if setting else 25) and not MonthlyTourProgram.objects.filter(employee=employee, month=next_month, year=next_year, status__in=['Pending', 'Approved']).exists():
            msg = f"Agale mahine ({next_month}/{next_year}) ka Tour Plan submit nahi hua hai (ya Reject ho gaya hai)!"
            if setting and setting.without_tourplan_dcr_block:
                messages.error(request, f"🚫 ACTION BLOCKED: {msg}")
                return redirect('mr_dashboard')
            alerts.append(msg)
            
        # Target Rule
        if today.day > (setting.target_approval_deadline_day if setting else 4) and not MonthlyTargetMaster.objects.filter(territory=employee.headquarter, month=curr_month, year=curr_year, status='Approved').exists():
            msg = f"Is mahine ({curr_month}/{curr_year}) ka Target abhi tak Approved nahi hua hai!"
            if setting and setting.without_tourplan_dcr_block:
                messages.error(request, f"🚫 ACTION BLOCKED: {msg}")
                return redirect('mr_dashboard')
            alerts.append(msg)

        # Previous Month Rules
        if worked_last_month:
            # Expense Rule
            if today.day > (setting.expense_submit_deadline_day if setting else 4) and not MonthlyExpenseReport.objects.filter(employee=employee, month=prev_month, year=prev_year, status__in=['Pending', 'Approved']).exists():
                msg = f"Pichle mahine ({prev_month}/{prev_year}) ki Expense Report pending ya Rejected hai!"
                if setting and setting.without_tourplan_dcr_block:
                    messages.error(request, f"🚫 ACTION BLOCKED: {msg}")
                    return redirect('mr_dashboard')
                alerts.append(msg)
                
            if today.day > (setting.sale_upload_deadline_day if setting else 4) and not PartyWiseSaleReport.objects.filter(employee=employee, month=prev_month, year=prev_year).exists():
                alerts.append(f"Pichle mahine ({prev_month}/{prev_year}) ki Party Wise Sale / Dr Wise entry pending hai!")

    # 🔵 B. STRICT RULES FOR MANAGER
    else:
        team_employees = get_full_team_employees(employee)
        subordinate_ids = team_employees.exclude(id=employee.id).values_list('id', flat=True)
        pending_items = []
        
        if MonthlyTourProgram.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Tour Plans')
        if MonthlyExpenseReport.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Expenses')
        if LeaveApplication.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): pending_items.append('Leaves')
        if GiftCampaignPlan.objects.filter(employee_id__in=subordinate_ids, status='Pending').exists(): 
            pending_items.append('Gift Campaigns')
        
        # Target Check (SQLite Safe JSON Check)
        sub_territories = Employee.objects.filter(id__in=subordinate_ids).exclude(headquarter__isnull=True).values_list('headquarter_id', flat=True)
        pending_targets = MonthlyTargetMaster.objects.filter(territory_id__in=sub_territories, status='Pending_Manager')
        has_pending_targets = any(employee.id not in (t.approved_by_managers or []) for t in pending_targets)
        if has_pending_targets:
            pending_items.append('Targets')
            
        # Free Claims Check (SQLite Safe JSON Check)
        pending_claims = FreeQtyClaimMaster.objects.filter(employee_id__in=subordinate_ids, status='Pending_Manager')
        has_pending_claims = any(employee.id not in (c.approved_by_managers or []) for c in pending_claims)
        if has_pending_claims:
            pending_items.append('Free Claims')
        
        if pending_items:
            msg = f"Aapki Team ki kuch requests ({', '.join(pending_items)}) approval ke liye pending hain! Kripya clear karein."
            if setting and setting.manager_pending_approval_block:
                messages.error(request, f"🚫 MANAGER DCR BLOCKED: {msg}")
                return redirect('manager_approvals')
            alerts.append(msg)

        # Manager's Own MTP Check 
        if not is_new_joiner and not MonthlyTourProgram.objects.filter(employee=employee, month=curr_month, year=curr_year, status__in=['Pending', 'Approved']).exists():
            msg = f"Aapka is mahine ({curr_month}/{curr_year}) ka Tour Plan system mein nahi hai (ya Reject ho gaya hai)!"
            if setting and setting.without_tourplan_dcr_block:
                messages.error(request, f"🚫 ACTION BLOCKED: {msg} Pehle is mahine ka MTP banakar submit karein.")
                return redirect('mr_dashboard')
            alerts.append(msg)
            
        # Manager's Own NEXT MONTH MTP Check
        if not is_new_joiner and today.day > (setting.mtp_approval_deadline_day if setting else 25) and not MonthlyTourProgram.objects.filter(employee=employee, month=next_month, year=next_year, status__in=['Pending', 'Approved']).exists():
            msg = f"Aapka agale mahine ({next_month}/{next_year}) ka Tour Plan submit nahi hua hai!"
            if setting and setting.without_tourplan_dcr_block:
                messages.error(request, f"🚫 ACTION BLOCKED: {msg}")
                return redirect('mr_dashboard')
            alerts.append(msg)

    # Data Fetching for Dropdowns
    if employee.designation == 'MR':
        team_employees = Employee.objects.filter(id=employee.id)
    else:
        team_employees = get_full_team_employees(employee)
        
    all_terr_ids = get_team_territory_ids(team_employees)
    all_route_ids = get_team_route_ids(team_employees, all_terr_ids, approved_only=True, include_tour_plan=True)
    yesterday_ds = DayStart.objects.filter(employee=employee, date=working_date - timezone.timedelta(days=1), night_stay=True).first()

    # ==========================================
    # 🌟 POST METHOD (Save Day Start)
    # ==========================================
    if request.method == "POST":
        sd = request.POST.get('date')
        tid = request.POST.get('territory')
        route_id = request.POST.get('primary_route')
        work_type = request.POST.get('work_type', 'Field Work')
        joint_id = request.POST.get('joint_worked_with')
        
        lat = request.POST.get('latitude') or None
        lng = request.POST.get('longitude') or None

        if not sd:
            messages.error(request, "⚠️ Date missing hai! Kripya page refresh karke wapas try karein.")
            return redirect('day_start')

        if DayEnd.objects.filter(employee=employee, date=sd, is_closed=True).exists():
            messages.error(request, f"⚠️ Aap {sd} ka Day End already kar chuke hain. Is date ko dobaara start nahi kiya ja sakta.")
            return redirect('mr_dashboard')

        try:
            joint_emp = Employee.objects.filter(id=joint_id).first() if joint_id else None
            
            day_start, created = DayStart.objects.get_or_create(
                employee=employee, 
                date=sd, 
                defaults={
                    'territory_id': tid if tid else None, 
                    'night_stay': request.POST.get('night_stay') == '1', 
                    'latitude': lat, 
                    'longitude': lng,
                    'work_type': work_type,
                    'joint_worked_with': joint_emp
                }
            )
            
            if created:
                if route_id and work_type == 'Field Work': 
                    day_start.routes.add(route_id)
                messages.success(request, f"🚀 {sd} ka Day Start successfully ho gaya!")
            else:
                messages.warning(request, f"⚠️ {sd} ka Day Start pehle se system mein maujood hai.")
                
            return redirect('mr_dashboard')
            
        except Exception as e:
            messages.error(request, f"❌ System Error: {str(e)}")
            return redirect('day_start')

    subordinates = list(team_employees.exclude(id=employee.id))
    superiors = employee.get_my_managers()
    joint_employees = subordinates + superiors

    return render(request, 'day_start.html', {
        'today_str': str(working_date),
        'territories': Territory.objects.filter(id__in=all_terr_ids).order_by('name') if all_terr_ids else Territory.objects.filter(company=employee.company).order_by('name'),
        'available_routes': Route.objects.filter(id__in=all_route_ids).select_related('territory').order_by('category', 'name'),
        'suggested_route': DailyTourPlan.objects.filter(mtp__employee=employee, date=working_date, mtp__status='Approved').select_related('route').first(),
        'is_return_day': yesterday_ds is not None,
        'joint_employees': joint_employees,
        'alerts': alerts
    })

@employee_required
def day_end_view(request, employee):
    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        messages.error(request, f"🚫 {stuck_day.date.strftime('%d %b %Y')} ka purana Day Start lock ho gaya hai. Admin se sampark karein — wo Django Admin se ye din manually close (DayEnd add) kar sakte hain.")
        return redirect('mr_dashboard')

    if not open_day: 
        messages.error(request, "Pehle Day Start karein!")
        return redirect('mr_dashboard')

    working_date = open_day.date
    day_closed = DayEnd.objects.filter(employee=employee, date=working_date, is_closed=True).exists()

    NO_EXPENSE_WORK_TYPES = ['Strike', 'Holiday', 'Leave']

    def calculate_expense(emp, ds_obj):
        if ds_obj.work_type in NO_EXPENSE_WORK_TYPES:
            return {'da': 0, 'ta': 0, 'distance': 0, 'territory_category': 'HQ', 'night_stay': ds_obj.night_stay, 'is_slab3': False}

        routes = ds_obj.routes.select_related('territory').all()
        night_stay = ds_obj.night_stay

        yesterday_ds = DayStart.objects.filter(
            employee=emp, date=ds_obj.date - timezone.timedelta(days=1)
        ).first()
        is_prev_night_stay = yesterday_ds.night_stay if yesterday_ds else False
        is_return_day = is_prev_night_stay and not night_stay

        if is_prev_night_stay and yesterday_ds.territory:
            start_hq = yesterday_ds.territory
        else:
            start_hq = emp.headquarter

        max_total = 0.0
        best_local = 0.0
        best_transit = 0.0
        is_outside_hq = False

        for r in routes:
            local_dist = float(r.distance_from_hq or 0)
            transit_dist = 0.0
            work_hq = r.territory

            if emp.headquarter and work_hq and emp.headquarter != work_hq:
                is_outside_hq = True

            if start_hq and work_hq and start_hq != work_hq:
                from SFA.models import HQDistance
                hq_conn = HQDistance.objects.filter(from_territory=start_hq, to_territory=work_hq).first()
                if not hq_conn:
                    hq_conn = HQDistance.objects.filter(from_territory=work_hq, to_territory=start_hq).first()
                transit_dist += float(hq_conn.distance_km) if hq_conn else 0.0

            if is_return_day and work_hq and emp.headquarter and work_hq != emp.headquarter:
                from SFA.models import HQDistance
                hq_conn_ret = HQDistance.objects.filter(from_territory=work_hq, to_territory=emp.headquarter).first()
                if not hq_conn_ret:
                    hq_conn_ret = HQDistance.objects.filter(from_territory=emp.headquarter, to_territory=work_hq).first()
                transit_dist += float(hq_conn_ret.distance_km) if hq_conn_ret else 0.0

            route_total = local_dist + transit_dist
            if route_total > max_total:
                max_total = route_total
                best_local = local_dist
                best_transit = transit_dist

        distance = max_total

        raw_cat = max(
            (r.category for r in routes),
            key=lambda x: {'OUTSTATION': 3, 'EX_HQ': 2, 'HQ': 1}.get(x, 0)
        ) if routes.exists() else 'HQ'

        if is_outside_hq:
            raw_cat = 'OUTSTATION' if (night_stay or is_prev_night_stay) else 'EX_HQ'

        if raw_cat == 'OUTSTATION':
            if is_return_day:
                eff_cat = 'EX_HQ'
            elif not night_stay and not is_prev_night_stay:
                eff_cat = 'EX_HQ'
            else:
                eff_cat = 'OUTSTATION'
        else:
            eff_cat = raw_cat

        try:
            da_rate = DARate.objects.get(company=emp.company, designation=emp.designation)
            da = {'HQ': da_rate.hq_da, 'EX_HQ': da_rate.exhq_da, 'OUTSTATION': da_rate.outstation_da}[eff_cat]
        except DARate.DoesNotExist:
            da = 0

        if not routes.exists() or eff_cat == 'HQ':
            return {'da': round(float(da), 2), 'ta': 0, 'distance': 0, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}

        changed_city_today = any(r.territory != start_hq for r in routes) if start_hq else False

        if is_return_day:
            transit_multiplier = 1
        elif eff_cat == 'OUTSTATION' and night_stay and not is_prev_night_stay:
            transit_multiplier = 1
        elif eff_cat == 'OUTSTATION' and night_stay and is_prev_night_stay:
            transit_multiplier = 1 if changed_city_today else 0
        else:
            transit_multiplier = 2

        billed_distance = (best_local * 2) + (best_transit * transit_multiplier)

        try:
            ta_rate = TARate.objects.get(company=emp.company, designation=emp.designation)
            if billed_distance == 0:
                return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
            elif distance <= ta_rate.slab1_upto_km:
                ta = round(billed_distance * float(ta_rate.slab1_rate), 2)
            elif distance <= ta_rate.slab2_upto_km:
                ta = round(billed_distance * float(ta_rate.slab2_rate), 2)
            else:
                return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': True}

            return {'da': round(float(da), 2), 'ta': ta, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
        except TARate.DoesNotExist:
            return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}

    exp_prev = calculate_expense(employee, open_day) if not day_closed else None

    if request.method == "POST" and not day_closed:
        DayEnd.objects.get_or_create(employee=employee, date=working_date, defaults={'is_closed': True, 'latitude': request.POST.get('latitude'), 'longitude': request.POST.get('longitude')})
        
        # 🌟 NAYA: DAY END HOTE HI DCR CALENDAR STATUS CLOSE & SUBMITTED MARK KARO
        DailyDCRStatus.objects.filter(employee=employee, date=working_date).update(is_submitted=True, is_open=False)
        
        master, _ = MonthlyExpenseReport.objects.get_or_create(employee=employee, month=working_date.month, year=working_date.year, defaults={'status': 'Draft'})

        defaults_dict = {
            'monthly_report': master, 'territory_category': exp_prev['territory_category'], 'night_stay': exp_prev['night_stay'],
            'distance_km': exp_prev['distance'], 'da_amount': exp_prev['da'], 'is_slab3': exp_prev['is_slab3'],
            'ta_amount': float(request.POST.get('actual_fare', 0) or 0) if exp_prev['is_slab3'] else exp_prev['ta'],
            'actual_fare': float(request.POST.get('actual_fare', 0) or 0) if exp_prev['is_slab3'] else 0,
            'misc_amount': float(request.POST.get('misc_amount', 0) or 0)
        }

        if request.FILES.get('misc_bill'): 
            defaults_dict['misc_bill'] = compress_photo(request.FILES.get('misc_bill'))

        DailyExpense.objects.update_or_create(employee=employee, date=working_date, defaults=defaults_dict)
        return redirect('mr_dashboard')

    daily_dcr = DailyDCR.objects.filter(employee=employee, date=working_date).first()

    today_dr_visits = 0
    today_chem_visits = 0
    today_samples = 0
    today_pob = 0

    if daily_dcr:
        today_dr_visits = daily_dcr.visits.filter(doctor__isnull=False).count()
        today_chem_visits = daily_dcr.visits.filter(chemist__isnull=False).count()

        agg = DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).aggregate(s=Sum('sample_qty'))
        today_samples = agg['s'] or 0

        for d in DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).select_related('product'):
            price = float(d.product.price) if getattr(d.product, 'price', None) else 0.0
            today_pob += (d.order_qty or 0) * price

    # 🌟 NAYA: Day Start me jo routes select/add hue the, unki territories nikal ke
    # duplicate-free list bana rahe hain — Day End screen par dikhane ke liye.
    territories_worked = []
    seen_territory_ids = set()
    for r in open_day.routes.select_related('territory').all():
        if r.territory and r.territory_id not in seen_territory_ids:
            seen_territory_ids.add(r.territory_id)
            territories_worked.append(r.territory)

    return render(request, 'day_end.html', {
        'today': working_date, 
        'day_closed': day_closed, 
        'expense_preview': exp_prev, 
        'open_day': open_day,
        'territories_worked': territories_worked,
        'today_dr_visits': today_dr_visits,
        'today_chem_visits': today_chem_visits,
        'today_samples': today_samples,
        'today_pob': round(today_pob, 2)
    })


@employee_required
def doctor_visit_view(request, employee, doc_id):
    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        messages.error(request, f"🚫 {stuck_day.date.strftime('%d %b %Y')} ka purana Day Start lock ho gaya hai. Admin se sampark karein.")
        return redirect('mr_dashboard')

    if not open_day: return redirect('mr_dashboard')
    doctor = get_object_or_404(Doctor, id=doc_id)
    
    if request.method == "POST":
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=open_day.date)
        
        # 🌟 NAYA: GEOFENCE BYPASS TRACKING (Agar entry backdate mein hai)
        setting = SystemSetting.objects.filter(company=employee.company).first()
        is_backdated = open_day.date < timezone.localdate()
        is_bypassed = False
        if is_backdated:
            # Agar backdate allowed hai without strict geofencing, then it's a bypass.
            if not setting or not setting.strict_geofence_for_backdate:
                is_bypassed = True
                
        visit = DCRVisit.objects.create(
            daily_dcr=daily_dcr, 
            route=doctor.route, 
            doctor=doctor, 
            remark=request.POST.get('remark', ''), 
            latitude=request.POST.get('latitude') or None, 
            longitude=request.POST.get('longitude') or None,
            geofence_bypassed=is_bypassed  # 🚩 Geofence exception marked!
        )
        
        # 1. PRODUCT SAMPLING & INVENTORY DEDUCTION
        for p in Product.objects.filter(company=employee.company):
            is_det = request.POST.get(f'detailed_{p.id}') == 'on'
            sq = int(request.POST.get(f'sample_{p.id}') or 0)
            oq = int(request.POST.get(f'order_{p.id}') or 0)
            
            if is_det or sq > 0 or oq > 0: 
                DCRProductDetail.objects.create(visit=visit, product=p, is_detailed=is_det, sample_qty=sq, order_qty=oq)
                
                # Bag se Sample minus karo!
                if sq > 0:
                    sample_inv = MRInventory.objects.filter(employee=employee, item__linked_product=p, item__item_type='Sample').first()
                    if sample_inv and sample_inv.stock_qty >= sq:
                        sample_inv.stock_qty -= sq
                        sample_inv.save()

        # 2. GIFTS/INPUTS DEDUCTION & ROI
        for key, value in request.POST.items():
            if key.startswith('promo_qty_') and value.strip():
                try:
                    qty_given = int(value)
                    if qty_given > 0:
                        item_id = int(key.replace('promo_qty_', ''))
                        inventory = MRInventory.objects.get(employee=employee, item_id=item_id)
                        
                        if inventory.stock_qty >= qty_given:
                            inventory.stock_qty -= qty_given
                            inventory.save()
                            
                            total_val = float(inventory.item.price) * qty_given
                            DoctorROILedger.objects.create(
                                date_given=open_day.date, 
                                doctor=doctor, 
                                employee=employee, 
                                item=inventory.item, 
                                quantity=qty_given, 
                                total_value=total_val,
                                visit=visit
                            )
                except (ValueError, MRInventory.DoesNotExist) as e:
                    pass
                    
        return redirect('mr_dashboard')
    
    my_inventory = MRInventory.objects.filter(employee=employee, stock_qty__gt=0).select_related('item')
    sample_stock_map = {inv.item.linked_product_id: inv.stock_qty for inv in my_inventory if inv.item.item_type == 'Sample' and inv.item.linked_product_id}
    
    products_with_stock = []
    for p in Product.objects.filter(company=employee.company):
        products_with_stock.append({
            'product': p,
            'stock': sample_stock_map.get(p.id, 0)
        })
        
    today = open_day.date
    approved_gift_ids = GiftCampaignPlan.objects.filter(
        employee=employee,
        doctor=doctor,
        status='Approved',
        month=today.month,
        year=today.year
    ).values_list('item_id', flat=True)

    gift_stock = []
    for inv in my_inventory:
        if inv.item.item_type == 'Sample':
            continue
        if inv.item.item_type == 'HighValue' and inv.item.id not in approved_gift_ids:
            continue
        gift_stock.append(inv)

    return render(request, 'dr_visit_form.html', {
        'doctor': doctor, 
        'products_data': products_with_stock,
        'gift_stock': gift_stock
    })


@employee_required
def chemist_visit_view(request, employee, chem_id):
    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        messages.error(request, f"🚫 {stuck_day.date.strftime('%d %b %Y')} ka purana Day Start lock ho gaya hai. Admin se sampark karein.")
        return redirect('mr_dashboard')

    if not open_day: return redirect('mr_dashboard')
    chemist = get_object_or_404(Chemist, id=chem_id)
    if request.method == "POST":
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=open_day.date)
        visit = DCRVisit.objects.create(daily_dcr=daily_dcr, route=chemist.route, chemist=chemist, latitude=request.POST.get('latitude'), longitude=request.POST.get('longitude'))
        for p in Product.objects.filter(company=employee.company):
            if int(request.POST.get(f'order_{p.id}', 0) or 0) > 0: DCRProductDetail.objects.create(visit=visit, product=p, sample_qty=0, order_qty=int(request.POST.get(f'order_{p.id}', 0)))
        return redirect('mr_dashboard')
    return render(request, 'chemist_visit.html', {'chemist': chemist, 'products': Product.objects.filter(company=employee.company), 'today': open_day.date})

@employee_required
def edit_visit_view(request, employee, visit_id):
    # 🌟 FIX: Ownership check (sirf apni hi visit edit ho sake) + DayEnd lock
    # check (jis din ka Day End ho gaya, us din ki visit edit nahi ho sakti)
    # — Delete Visit jaisa hi rule.
    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee)
    visit_date = visit.daily_dcr.date
    if DayEnd.objects.filter(employee=employee, date=visit_date, is_closed=True).exists():
        messages.error(request, "⚠️ Ye visit lock ho gayi hai (Day End ho chuka hai), ab edit nahi ho sakti.")
        return redirect('mr_dashboard')

    products = Product.objects.filter(company=employee.company)
    if request.method == "POST":
        visit.remark = request.POST.get('remark', ''); visit.save()
        for p in products:
            is_det, sq, oq = request.POST.get(f'detailed_{p.id}') == 'on', int(request.POST.get(f'sample_{p.id}') or 0), int(request.POST.get(f'order_{p.id}') or 0)
            if is_det or sq > 0 or oq > 0:
                d, c = DCRProductDetail.objects.get_or_create(visit=visit, product=p, defaults={'is_detailed': is_det, 'sample_qty': sq, 'order_qty': oq})
                if not c: d.is_detailed, d.sample_qty, d.order_qty = is_det, sq, oq; d.save()
            else: DCRProductDetail.objects.filter(visit=visit, product=p).delete()
        return redirect('mr_dashboard')
    ed = {d.product_id: d for d in DCRProductDetail.objects.filter(visit=visit)}
    pwd = [{'product': p, 'is_detailed': ed[p.id].is_detailed if p.id in ed else False, 'sample_qty': ed[p.id].sample_qty if p.id in ed else '', 'order_qty': ed[p.id].order_qty if p.id in ed else ''} for p in products]
    return render(request, 'edit_visit.html', {'visit': visit, 'products_with_data': pwd, 'customer_name': visit.doctor.name if visit.doctor else visit.chemist.name, 'customer_type': 'Doctor' if visit.doctor else 'Chemist'})

@employee_required
def delete_visit_view(request, employee, visit_id):
    # 🌟 FIX: Pehle visit khud dhoondo (employee-ownership check ke saath),
    # phir USI VISIT KI APNI DATE ka DayEnd check karo — 'aaj' (timezone.localdate())
    # hardcode nahi karna, warna kal/pichle din ki visit (jiska Day End abhi
    # tak nahi hua) delete nahi ho payegi, jabki use abhi tak "open" hi rehna chahiye.
    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee)
    visit_date = visit.daily_dcr.date
    if not DayEnd.objects.filter(employee=employee, date=visit_date, is_closed=True).exists():
        visit.delete()
    return redirect('mr_dashboard')
from SFA.models import CompanyNotice, SystemNotification, DirectMessage

# ==============================================================================
# 📢 HUB: NOTICES, NOTIFICATIONS & MESSAGES
# ==============================================================================

# views.py ke upar import
# 🌟 NAYA HELPER FUNCTION: Environment variable se file banane ke liye
def get_firebase_cred_path():
    # 1. Pehle local file check karein (Pydroid/mobile ke liye)
    local_path = os.path.join(settings.BASE_DIR, 'firebase_key.json')
    if os.path.exists(local_path):
        return local_path
    
    # 2. Agar local file nahi hai (Render par), toh Env Variable check karein
    tmp_path = '/tmp/firebase_key.json' # Render par temporary file yahan banegi
    if not os.path.exists(tmp_path):
        env_creds = os.environ.get('FIREBASE_CREDENTIALS')
        if env_creds:
            try:
                # JSON string ko file mein likh dein
                with open(tmp_path, 'w') as f:
                    f.write(env_creds)
            except Exception as e:
                print(f"Error writing Firebase key: {e}")
    return tmp_path

# 🌟 NAYA HELPER FUNCTION: Project ID ke liye (Taaki hardcode na karna pade)
def get_firebase_project_id():
    env_creds = os.environ.get('FIREBASE_CREDENTIALS')
    if env_creds:
        try:
            return json.loads(env_creds).get('project_id', '')
        except:
            pass
    return "your-firebase-project-id" # Local ke liye fallback
from django.contrib import messages
from django.shortcuts import render, redirect
from django.conf import settings
import os
# 🌟 IMPORTS ADD KARO
# 🌟 PERMANENT FIX: Agar file server par na ho, toh fake function bana do
try:
    from fcm_sender import send_fcm_push
except ImportError:
    def send_fcm_push(*args, **kwargs):
        print("FCM Sender not available on this server. Skipping push.")
        pass
from SFA.models import DeviceToken, CompanyNotice, SystemNotification
from SFA.decorators import employee_required

@employee_required
def notice_board_view(request, employee):
    is_admin = employee.designation in ['Admin', 'System Administrator']

    # 🚨 ADMIN BROADCAST LOGIC
    if request.method == 'POST' and is_admin:
        title = request.POST.get('title')
        body = request.POST.get('body') 
        
        if title and body:
            # 1. Notice Create karo
            CompanyNotice.objects.create(title=title, body=body, created_by=employee, company=employee.company)
            
            # 2. 🌟 FIX: Sabhi employees ke liye SystemNotification banao taaki Flutter app me dikhe
            company_emps = Employee.objects.filter(company=employee.company)
            notif_objs = [
                SystemNotification(
                    employee=emp,  # NOTE: Model field 'employee' hai, isliye 'emp=emp' ki jagah 'employee=emp' likha hai
                    title=f"📢 {title}",
                    message=body
                ) for emp in company_emps
            ]
            SystemNotification.objects.bulk_create(notif_objs)
            
            # 3. 🌟 FCM Push Notification Bhejna
            tokens = list(DeviceToken.objects.filter(employee__company=employee.company).values_list('token', flat=True))
            
            # 🌟 Dynamic Project ID aur Cred Path
            project_id = get_firebase_project_id()
            cred_path = get_firebase_cred_path()
            
            # Try-except taaki FCM fail hone par DB save aur UI flow disturb na ho
            try:
                if os.path.exists(cred_path):
                    send_fcm_push(title, body, tokens, project_id, cred_path)
                else:
                    print("Firebase credentials file not found!")
            except Exception as e:
                print(f"FCM Push Error: {e}")
                    
            messages.success(request, "📢 Notice successfully broadcast ho gaya!")
            return redirect('notice_board')

    # Latest notices sabse upar
    notices = CompanyNotice.objects.filter(created_by__company=employee.company).order_by('-id')

    # Mark all system notifications as read
    SystemNotification.objects.filter(employee=employee, is_read=False).update(is_read=True)

    return render(request, 'notice_board.html', {
        'notices': notices,
        'is_admin': is_admin,
    })
# 🌟 NAYA: Web Inbox View
@employee_required
def web_inbox_view(request, employee):
    received_msgs = InternalMessage.objects.filter(receiver=employee).order_by('-sent_at')
    sent_msgs = InternalMessage.objects.filter(sender=employee).order_by('-sent_at')
    
    # Jaise hi page khule, received messages read ho jayein
    received_msgs.filter(is_read=False).update(is_read=True)
    
    return render(request, 'message_list.html', {
        'received_msgs': received_msgs,
        'sent_msgs': sent_msgs
    })

# 🌟 NAYA: Web Message Detail View
@employee_required
def web_message_detail_view(request, employee, msg_id):
    # Message fetch karein (sirf sender ya receiver hi dekh sake)
    msg = get_object_or_404(InternalMessage, id=msg_id)
    if msg.receiver_id != employee.id and msg.sender_id != employee.id:
        messages.error(request, "You are not authorized to view this message.")
        return redirect('web_inbox')
    
    # Agar receiver khul raha hai aur unread hai, toh read mark kar do
    if msg.receiver_id == employee.id and not msg.is_read:
        msg.is_read = True
        msg.save()
        
    return render(request, 'message_detail.html', {'msg': msg})


# 🌟 UPDATE: Web Compose View (Reply/Forward handle karega)
@employee_required
def web_compose_view(request, employee):
    # Reply aur Forward ke liye pre-fill data
    reply_to_msg = None
    forward_to_msg = None
    
    if request.method == 'GET':
        reply_to_id = request.GET.get('reply_to')
        forward_to_id = request.GET.get('forward_to')
        
        if reply_to_id:
            reply_to_msg = get_object_or_404(InternalMessage, id=reply_to_id)
        elif forward_to_id:
            forward_to_msg = get_object_or_404(InternalMessage, id=forward_to_id)
            
    elif request.method == 'POST':
        # 🌟 FIX: Multiple "To" recipients ab supported hain
        receiver_ids = request.POST.getlist('receiver_ids')
        subject = request.POST.get('subject')
        body = request.POST.get('body')

        if receiver_ids and subject:
            files = request.FILES.getlist('attachments')

            # 🌟 FIX: Pehle saare recipients ke naam nikal lo, taaki har copy mein
            # poori "To" list dikhe — recipient ko sirf apna naam nahi, sabka pata chale
            recipients = list(Employee.objects.filter(id__in=receiver_ids))
            recipients_display = ', '.join(r.name for r in recipients)

            sent_count = 0
            for receiver in recipients:
                msg = InternalMessage.objects.create(
                    sender=employee,
                    receiver=receiver,
                    subject=subject,
                    body=body,
                    all_recipients=recipients_display
                )
                for f in files:
                    f.seek(0)  # Har recipient ke liye file pointer reset karna zaroori hai
                    MessageAttachment.objects.create(message=msg, file=f)
                sent_count += 1

            if sent_count > 1:
                messages.success(request, f"✉️ Mail sent to {sent_count} recipients!")
            else:
                messages.success(request, "✉️ Mail sent successfully!")
            return redirect('web_inbox')
    
    # Contacts ke liye Hierarchy Logic
    managers = employee.get_my_managers(include_inactive=False)
    admins = list(Employee.objects.filter(company=employee.company, designation='Admin', is_active=True))
    
    def get_subs(emp):
        subs = []
        direct = Employee.objects.filter(manager=emp, is_active=True)
        for s in direct:
            subs.append(s)
            subs.extend(get_subs(s))
        return subs
        
    subordinates = get_subs(employee) if employee.designation != 'MR' else []
    all_emps = managers + subordinates + admins
    unique_emps = {e.id: e for e in all_emps if e.id != employee.id}
    contacts = list(unique_emps.values())

    return render(request, 'message_compose.html', {
        'contacts': contacts,
        'reply_to_msg': reply_to_msg,
        'forward_to_msg': forward_to_msg
    })
@employee_required
def notification_list_view(request, employee):
    # Employee ke saare alerts uthao
    notifications = SystemNotification.objects.filter(employee=employee).order_by('-created_at')
    
    # Jaise hi MR page kholega, sabhi "Unread" notifications ko "Read" mark kar do (Red dot hat jayega)
    notifications.filter(is_read=False).update(is_read=True)
    
    return render(request, 'notification_list.html', {
        'notifications': notifications
    })
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from SFA.models import Employee
from SFA.decorators import employee_required
from SFA.services.team import get_full_team_employees

@employee_required
def profile_view(request, employee):
    # 🌟 Agar Manager kisi aur ka profile dekh raha hai (Organogram ya Dropdown se)
    emp_id = request.GET.get('employee_id')
    if emp_id:
        target_emp = get_object_or_404(Employee, id=emp_id, company=employee.company)
        team_members = get_full_team_employees(employee)
        managers = employee.get_my_managers()
        allowed_ids = set(team_members.values_list('id', flat=True)) | set([m.id for m in managers])
        
        if target_emp.id not in allowed_ids and target_emp.id != employee.id:
            messages.error(request, "Aap sirf apni team ki profile dekh sakte hain.")
            return redirect('profile')
            
        target_employee = target_emp
    else:
        target_employee = employee

    # 🌟 Sirf khud ki profile edit/password change ho sakti hai
    if request.method == "POST" and target_employee.id == employee.id:
        action = request.POST.get('action')

        if action == 'update_profile':
            employee.phone = request.POST.get('phone', employee.phone)
            employee.address = request.POST.get('address', employee.address)
            
            # Personal
            employee.dob = request.POST.get('dob') or None
            employee.anniversary = request.POST.get('anniversary') or None
            employee.blood_group = request.POST.get('blood_group') or None
            employee.emergency_contact = request.POST.get('emergency_contact') or None
            employee.permanent_address = request.POST.get('permanent_address') or None
            
            # Father
            employee.father_name = request.POST.get('father_name') or None
            employee.father_dob = request.POST.get('father_dob') or None
            employee.father_mobile = request.POST.get('father_mobile') or None
            employee.father_occupation = request.POST.get('father_occupation') or None
            
            # Mother
            employee.mother_name = request.POST.get('mother_name') or None
            employee.mother_dob = request.POST.get('mother_dob') or None
            employee.mother_mobile = request.POST.get('mother_mobile') or None
            employee.mother_occupation = request.POST.get('mother_occupation') or None
            
            # Spouse
            employee.spouse_name = request.POST.get('spouse_name') or None
            employee.spouse_dob = request.POST.get('spouse_dob') or None
            employee.spouse_mobile = request.POST.get('spouse_mobile') or None
            employee.spouse_occupation = request.POST.get('spouse_occupation') or None
            
            # Children
            employee.child1_name = request.POST.get('child1_name') or None
            employee.child1_dob = request.POST.get('child1_dob') or None
            employee.child2_name = request.POST.get('child2_name') or None
            employee.child2_dob = request.POST.get('child2_dob') or None
            
            if 'photo' in request.FILES:
                from SFA.views.core import compress_photo # Image compression helper
                employee.photo = compress_photo(request.FILES['photo'])
                
            employee.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')

        elif action == 'change_password':
            old_pwd = request.POST.get('old_password')
            new_pwd = request.POST.get('new_password')
            confirm_pwd = request.POST.get('confirm_password')
            
            if new_pwd != confirm_pwd:
                messages.error(request, "New passwords do not match!")
            elif not request.user.check_password(old_pwd):
                messages.error(request, "Old password is wrong!")
            else:
                request.user.set_password(new_pwd)
                request.user.save()
                update_session_auth_hash(request, request.user) # Login session break na ho
                messages.success(request, "Password changed successfully!")
            return redirect('profile')

    # Team Data fetch for TEAM TAB
    team_members = []
    if target_employee.designation != 'MR':
        team_members = Employee.objects.filter(manager=target_employee, is_active=True).order_by('name')

    return render(request, 'profile.html', {
        'employee': target_employee, 
        'team_members': team_members
    })

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction # 🌟 ENTERPRISE MAGIC
from SFA.models import EmployeeTransferLog  # 🌟 Transfer/Resign audit log
# Make sure to import your models: Employee, Doctor, Chemist


def _transfer_employee_data(old_emp, new_emp):
    """
    🌟 SHARED CORE: Ek employee ka saara 'ongoing ownership' data doosre
    employee ko transfer karta hai. Ye function 2 jagah se use hoti hai:
      1. transfer_data_view  -> Old (real) Employee se New (real) Employee
      2. resign_employee_view -> Old (real) Employee se Vacant_<HQ> Dummy
      3. Jab naya Employee aaye     -> Vacant_<HQ> Dummy se New (real) Employee

    Isliye 'old_emp'/'new_emp' ka matlab hamesha "real insaan" nahi hai —
    dono me se koi bhi Dummy (is_placeholder=True) ho sakta hai.

    Caller transaction.atomic() ke andar hi ise call kare.
    Returns: dict with counts + skipped info, taaki caller apna message bana sake.
    """
    # 1. Doctors Transfer karein
    doc_count = Doctor.objects.filter(allocated_to=old_emp).update(allocated_to=new_emp)

    # 2. Chemists Transfer karein
    chem_count = Chemist.objects.filter(allocated_to=old_emp).update(allocated_to=new_emp)

    # 3. Manager's Team Transfer (Agar purana banda Manager tha)
    team_count = Employee.objects.filter(manager=old_emp).update(manager=new_emp)

    # 4. Party-wise Sale Report transfer karein (Dr-wise sale isi se
    #    derive hoti hai, DoctorRxMapping -> party_line -> report.employee
    #    ke through — isliye alag se kuch karne ki zaroorat nahi)
    sale_count = PartyWiseSaleReport.objects.filter(employee=old_emp).update(employee=new_emp)

    # 5. Gift Campaign Plan transfer karein (future/ongoing distribution
    #    plans naye employee ke account se continue honge)
    gift_count = GiftCampaignPlan.objects.filter(employee=old_emp).update(employee=new_emp)

    # 6. Free Qty Claims transfer — yahan unique_together
    #    ('employee', 'stockist', 'month', 'year') hai, isliye direct
    #    bulk update nahi kar sakte (conflict aa sakta hai agar naye
    #    employee ka usi stockist/month/year ka claim already ho).
    #    Conflict wale claims ko skip karte hain aur message me bata
    #    dete hain, taaki Admin manually dekh sake.
    claim_count, claim_skipped = 0, 0
    for claim in FreeQtyClaimMaster.objects.filter(employee=old_emp):
        clash = FreeQtyClaimMaster.objects.filter(
            employee=new_emp, stockist=claim.stockist,
            month=claim.month, year=claim.year
        ).exists()
        if clash:
            claim_skipped += 1
        else:
            claim.employee = new_emp
            claim.save(update_fields=['employee'])
            claim_count += 1

    # 🌟 NOTE: MRInventory (samples/gifts ka physical stock) jaanbhuj
    # kar transfer NAHI kiya ja raha. Jab tak old employee/dummy physically
    # apna stock naye employee ko handover na kare, system me bhi wo
    # stock wahi ke naam rehna chahiye — warna inventory galat dikhegi.
    # Physical handover ke baad ye alag se, manually ya kisi dedicated
    # "Stock Handover" feature se transfer karna.

    return {
        'doc_count': doc_count, 'chem_count': chem_count, 'team_count': team_count,
        'sale_count': sale_count, 'gift_count': gift_count,
        'claim_count': claim_count, 'claim_skipped': claim_skipped,
    }


@login_required
def transfer_data_view(request):
    # 🔒 Security: Sirf Admin ya NSM hi ye kar sakta hai
    if request.user.employee.designation not in ['Admin', 'NSM']:
        messages.error(request, "⚠️ Aapko Data Handover karne ka access nahi hai.")
        return redirect('mr_dashboard') # Ya jo bhi aapka home URL ho

    # 🌟 AJAX: "Old Employee" select hote hi stats box ke liye live counts
    # bhejta hai (Doctors / Chemists / Team) — template ka JS isi endpoint
    # ko ?get_stats=1&emp_id=<id> se call karta hai.
    if request.method == "GET" and request.GET.get('get_stats') == '1':
        emp_id = request.GET.get('emp_id')
        try:
            emp = Employee.objects.get(id=emp_id)
            data = {
                'success': True,
                'doctors': Doctor.objects.filter(allocated_to=emp).count(),
                'chemists': Chemist.objects.filter(allocated_to=emp).count(),
                'team': Employee.objects.filter(manager=emp).count(),
            }
        except Employee.DoesNotExist:
            data = {'success': False}
        return JsonResponse(data)

    # Old Employee dropdown: jo bhi abhi active hai (real employees + Vacant
    # placeholders dono) — Vacant_<HQ> ko bhi "Old" select karke aage transfer
    # kiya ja sakta hai jab naya Employee mile.
    old_employees = Employee.objects.filter(company=request.user.employee.company, is_active=True).order_by('name')
    # New Employee dropdown: sirf real, active, non-placeholder employees —
    # data sirf kisi asli insaan ko hi final transfer hona chahiye.
    new_employees = Employee.objects.filter(company=request.user.employee.company, is_active=True, is_placeholder=False).order_by('name')
    recent_logs = EmployeeTransferLog.objects.filter(transferred_by__company=request.user.employee.company).select_related('new_employee', 'transferred_by').order_by('-transfer_date')[:15]

    if request.method == "POST":
        old_emp_id = request.POST.get('old_employee')
        new_emp_id = request.POST.get('new_employee')
        old_emp_status_raw = request.POST.get('old_emp_status', 'Resigned')

        # Template ke dropdown options (Resigned/Terminated/Transferred/Retired)
        # ko humare Employee.employment_status choices se map karte hain.
        STATUS_MAP = {
            'Resigned': 'resigned',
            'Terminated': 'terminated',
            'Transferred': 'transferred',
            'Retired': 'retired',
        }
        new_status = STATUS_MAP.get(old_emp_status_raw, 'resigned')

        if old_emp_id == new_emp_id:
            messages.warning(request, "⚠️ Old aur New employee same nahi ho sakte!")
            return redirect('transfer_data')

        try:
            # 🌟 transaction.atomic(): Agar koi ek line fail hui, toh sabkuch rollback ho jayega!
            with transaction.atomic(): 
                old_emp = Employee.objects.get(id=old_emp_id)
                new_emp = Employee.objects.get(id=new_emp_id)

                r = _transfer_employee_data(old_emp, new_emp)

                # Old Employee ko Inactive (Soft-Delete) karein.
                # 🌟 Agar old_emp khud ek Vacant Dummy tha (jiska kaam ho gaya
                # ab naya Employee mil gaya), to status hamesha 'archived' — Admin
                # ne jo dropdown me select kiya wo sirf REAL employee ke
                # resign-reason ke liye maana jata hai, Dummy ke liye nahi.
                old_emp.is_active = False
                old_emp.leaving_date = timezone.now().date()
                old_emp.employment_status = 'archived' if old_emp.is_placeholder else new_status
                old_emp.save()

                # Old Django User ka login block karein (agar tha)
                if old_emp.user:
                    old_emp.user.is_active = False
                    old_emp.user.save()

                success_msg = f"🎉 Handover Complete! {r['doc_count']} Doctors, {r['chem_count']} Chemists, {r['team_count']} Team Members, {r['sale_count']} Sale Reports, {r['gift_count']} Gift Plans, aur {r['claim_count']} Free Qty Claims successfully '{new_emp.name}' ko transfer ho gaye."
                if r['claim_skipped']:
                    success_msg += f" ⚠️ {r['claim_skipped']} Free Qty Claims skip hue (same stockist/month ka claim '{new_emp.name}' ke paas already maujood hai — unhe manually merge karein)."
                success_msg += f" '{old_emp.name}' ka account inactive kar diya gaya hai. Note: Samples/Gifts ka physical stock (MRInventory) transfer NAHI hua hai — wo physical handover ke baad alag se karein."
                messages.success(request, success_msg)

                # 🌟 Audit Log: kisne, kab, kis-se-kis-ko, kitna data transfer kiya
                EmployeeTransferLog.objects.create(
                    transferred_by=request.user.employee,
                    old_employee_name=old_emp.name,
                    new_employee=new_emp,
                    details=(
                        f"Doctors:{r['doc_count']}, Chemists:{r['chem_count']}, "
                        f"Team:{r['team_count']}, SaleReports:{r['sale_count']}, "
                        f"GiftPlans:{r['gift_count']}, FreeQtyClaims:{r['claim_count']} "
                        f"(skipped:{r['claim_skipped']}), "
                        f"OldEmpStatus:{old_emp.employment_status}"
                    ),
                )
                
        except Exception as e:
            messages.error(request, f"❌ Data transfer fail ho gaya: {str(e)}")
            
        return redirect('transfer_data')

    return render(request, 'transfer_data.html', {
        'old_employees': old_employees,
        'new_employees': new_employees,
        'recent_logs': recent_logs,
    })


def _create_vacant_dummy_and_offload(old_emp):
    """
    🌟 SHARED: Kisi employee ke 'current role' ka saara ongoing data ek naye
    'Vacant_<Designation>_<HQ>_<id>' placeholder employee ko transfer kar
    deta hai, aur wahi naya dummy object return karta hai.
    Use hota hai: resign_employee_view (jab employee company chhode) aur
    promote_employee_view (jab employee ka apna PURANA role data hold
    karna ho, kyunki wo ab naye designation me promote ho raha hai).
    Caller transaction.atomic() ke andar hi ise call kare.
    """
    hq_name = old_emp.headquarter.name if old_emp.headquarter else "NoHQ"
    dummy_code = f"VACANT-{old_emp.employee_code}-{old_emp.id}"
    # 🌟 Designation + id dono naam me — taaki ek hi HQ se MR/ABM/RSM sab
    # resign/promote ho jayein to bhi naam clash na ho aur pehchanna aasan rahe.
    dummy_name = f"Vacant_{old_emp.designation}_{hq_name}_{old_emp.id}"

    dummy = Employee.objects.create(
        name=dummy_name,
        employee_code=dummy_code,
        designation=old_emp.designation,
        manager=old_emp.manager,
        headquarter=old_emp.headquarter,
        phone="0000000000",
        joining_date=timezone.now().date(),
        is_active=True,                # 🌟 Listing/reports me normal dikhega
        employment_status='vacant',
        is_placeholder=True,
        user=None,                      # 🌟 Login possible nahi — koi User linked nahi
    )
    r = _transfer_employee_data(old_emp, dummy)
    return dummy, r


@login_required
def promote_employee_view(request):
    """
    🌟 NAYA VIEW: Existing employee ko upar ke designation me promote karna
    — "Resign+Naya Employee" wala flow promotion ke liye GALAT hai, kyunki
    wahi insaan hai, do alag log nahi. Yahan EK CLICK me:
      1. (Agar employee ke paas apna PURANA-role ka data hai) — usse
         _create_vacant_dummy_and_offload() se ek naye Vacant dummy ko
         offload kar dete hain (jaisa resign karte waqt hota hai), taaki
         promoted employee ke account me purana aur naya data mix na ho.
      2. Employee.designation aur manager update karte hain (naya manager
         = jis Vacant position ka data inherit kar raha hai, uska manager).
      3. Target Vacant dummy (jis position ko fill kiya ja raha hai) ka
         saara data is employee ko transfer kar dete hain — phir dummy
         archive ho jata hai.
    Sab kuch transaction.atomic() ke andar, EmployeeTransferLog me 2 entries
    (offload + inherit) ban sakti hain.
    """
    if request.user.employee.designation not in ['Admin', 'NSM']:
        messages.error(request, "⚠️ Aapko ye action karne ka access nahi hai.")
        return redirect('mr_dashboard')

    DESIGNATION_LEVELS = ['MR', 'ABM', 'RBM', 'ZBM', 'NSM', 'Admin']

    # AJAX: naya designation select hote hi, USI designation ke Vacant
    # dummies ki list bhejta hai (smart dropdown).
    if request.method == "GET" and request.GET.get('get_vacancies') == '1':
        new_designation = request.GET.get('designation', '')
        vacancies = Employee.objects.filter(
    company=request.user.employee.company, is_active=True, is_placeholder=True, designation=new_designation
).select_related('headquarter')

        data = {
            'success': True,
            'vacancies': [
                {'id': v.id, 'label': f"{v.name} ({v.headquarter.name if v.headquarter else 'No HQ'})"}
                for v in vacancies
            ],
        }
        return JsonResponse(data)

    # AJAX: employee select hote hi uske current data-counts dikhane ke liye
    if request.method == "GET" and request.GET.get('get_stats') == '1':
        emp_id = request.GET.get('emp_id')
        try:
            emp = Employee.objects.get(id=emp_id)
            data = {
                'success': True,
                'designation': emp.designation,
                'doctors': Doctor.objects.filter(allocated_to=emp).count(),
                'chemists': Chemist.objects.filter(allocated_to=emp).count(),
                'team': Employee.objects.filter(manager=emp).count(),
            }
        except Employee.DoesNotExist:
            data = {'success': False}
        return JsonResponse(data)

    promotable_employees = Employee.objects.filter(company=request.user.employee.company, is_active=True, is_placeholder=False).exclude(designation='Admin').order_by('name')

    if request.method == "POST":
        emp_id = request.POST.get('employee')
        new_designation = request.POST.get('new_designation')
        vacancy_id = request.POST.get('vacancy')

        if new_designation not in DESIGNATION_LEVELS:
            messages.error(request, "⚠️ Invalid designation select kiya gaya.")
            return redirect('promote_employee')

        try:
            with transaction.atomic():
                emp = Employee.objects.select_related('headquarter', 'manager').get(id=emp_id)
                vacancy = Employee.objects.select_related('manager', 'headquarter').get(id=vacancy_id, is_placeholder=True)

                if emp.is_placeholder:
                    messages.warning(request, "⚠️ Vacant placeholder ko promote nahi kiya ja sakta.")
                    return redirect('promote_employee')

                if DESIGNATION_LEVELS.index(new_designation) <= DESIGNATION_LEVELS.index(emp.designation):
                    messages.warning(request, f"⚠️ Naya designation '{new_designation}' current designation '{emp.designation}' se upar hona chahiye.")
                    return redirect('promote_employee')

                offload_msg_part = ""
                # Step 1: Agar employee ke paas apna PURANA role ka data hai,
                # to use naye Vacant dummy me offload karo — taaki promotion
                # ke baad uske account me purana + naya data mix na ho jaye.
                old_doc_count = Doctor.objects.filter(allocated_to=emp).count()
                old_chem_count = Chemist.objects.filter(allocated_to=emp).count()
                old_team_count = Employee.objects.filter(manager=emp).count()
                if old_doc_count or old_chem_count or old_team_count:
                    old_dummy, r_old = _create_vacant_dummy_and_offload(emp)
                    offload_msg_part = (
                        f" Iska purana data ('{r_old['doc_count']}' Doctors, '{r_old['chem_count']}' Chemists, "
                        f"'{r_old['team_count']}' Team) '{old_dummy.name}' (naya placeholder) ko offload ho gaya."
                    )
                    EmployeeTransferLog.objects.create(
                        transferred_by=request.user.employee,
                        old_employee_name=emp.name,
                        new_employee=old_dummy,
                        details=(
                            f"[PROMOTION OFFLOAD] {emp.name} ka purana role ({emp.designation}) ka data "
                            f"offload, Doctors:{r_old['doc_count']}, Chemists:{r_old['chem_count']}, "
                            f"Team:{r_old['team_count']}"
                        ),
                    )

                # Step 2: Designation + manager update — naya manager wahi
                # hoga jo target vacancy ka manager tha.
                old_designation = emp.designation
                emp.designation = new_designation
                emp.manager = vacancy.manager
                if vacancy.headquarter:
                    emp.headquarter = vacancy.headquarter
                emp.save()

                # Step 3: Target vacancy ka data is employee ko transfer karo.
                r_new = _transfer_employee_data(vacancy, emp)
                vacancy.is_active = False
                vacancy.employment_status = 'archived'
                vacancy.save()

                EmployeeTransferLog.objects.create(
                    transferred_by=request.user.employee,
                    old_employee_name=vacancy.name,
                    new_employee=emp,
                    details=(
                        f"[PROMOTION] {emp.name} promoted {old_designation} -> {new_designation}. "
                        f"Doctors:{r_new['doc_count']}, Chemists:{r_new['chem_count']}, "
                        f"Team:{r_new['team_count']}, SaleReports:{r_new['sale_count']}, "
                        f"GiftPlans:{r_new['gift_count']}, FreeQtyClaims:{r_new['claim_count']} "
                        f"(skipped:{r_new['claim_skipped']})"
                    ),
                )

                messages.success(
                    request,
                    f"🎉 '{emp.name}' ko '{old_designation}' se '{new_designation}' promote kar diya gaya. "
                    f"'{vacancy.name}' ka data ('{r_new['doc_count']}' Doctors, '{r_new['chem_count']}' Chemists, "
                    f"'{r_new['team_count']}' Team, '{r_new['sale_count']}' Sale Reports, "
                    f"'{r_new['gift_count']}' Gift Plans, '{r_new['claim_count']}' Free Qty Claims) "
                    f"ab '{emp.name}' ke account me hai." + offload_msg_part
                )

        except Employee.DoesNotExist:
            messages.error(request, "❌ Employee ya Vacancy nahi mila.")
        except Exception as e:
            messages.error(request, f"❌ Promotion fail ho gaya: {str(e)}")

        return redirect('promote_employee')

    return render(request, 'promote_employee.html', {
        'employees': promotable_employees,
        'designation_levels': DESIGNATION_LEVELS,
    })


@login_required
def resign_employee_view(request):
    """
    🌟 NAYA VIEW: Jab koi employee resign/retire/terminate ho aur turant
    replacement na mile, to ye view EK CLICK me:
      1. Ek 'Vacant_<Designation>_<HQ>_<id>' Dummy employee banata hai
         (same designation, headquarter, manager — taaki Manager ki team
         listing aur reports me HQ ka data dikhna band na ho jaye).
      2. Resigning employee ka saara ongoing data (Doctor, Chemist, Team,
         Sale Reports, Gift Plans, Free Qty Claims) Dummy ko transfer kar
         deta hai — _create_vacant_dummy_and_offload() reuse karke.
      3. Asli employee ko is_active=False + employment_status set kar deta
         hai (resigned/retired/terminated — jo Admin select kare).

    Jab naya Employee mil jaye, Admin normal 'transfer_data_view' use karke
    Dummy -> New Employee transfer kar dega (Dummy dropdown me already
    is_active=True hone ki wajah se dikh jayegi).
    """
    if request.user.employee.designation not in ['Admin', 'NSM']:
        messages.error(request, "⚠️ Aapko ye action karne ka access nahi hai.")
        return redirect('mr_dashboard')

    # Sirf un employees ko dropdown me dikhayenge jo abhi active hain aur
    # khud Dummy/placeholder nahi hain (Dummy ko 'resign' karne ka koi
    # matlab nahi banta).
    resignable_employees = Employee.objects.filter(company=request.user.employee.company, is_active=True, is_placeholder=False).order_by('name')

    if request.method == "POST":
        emp_id = request.POST.get('employee')
        reason = request.POST.get('employment_status', 'resigned')  # resigned/retired/terminated

        if reason not in ('resigned', 'retired', 'terminated'):
            reason = 'resigned'

        try:
            with transaction.atomic():
                old_emp = Employee.objects.select_related('headquarter', 'manager').get(id=emp_id)

                if old_emp.is_placeholder:
                    messages.warning(request, "⚠️ Ye already ek Vacant placeholder hai, ise resign nahi kiya ja sakta.")
                    return redirect('resign_employee')

                dummy, r = _create_vacant_dummy_and_offload(old_emp)

                old_emp.is_active = False
                old_emp.leaving_date = timezone.now().date()
                old_emp.employment_status = reason
                old_emp.save()

                if old_emp.user:
                    old_emp.user.is_active = False
                    old_emp.user.save()

                messages.success(
                    request,
                    f"✅ '{old_emp.name}' ko '{reason}' mark kar diya gaya. "
                    f"Iska data ('{r['doc_count']}' Doctors, '{r['chem_count']}' Chemists, "
                    f"'{r['team_count']}' Team Members, '{r['sale_count']}' Sale Reports, "
                    f"'{r['gift_count']}' Gift Plans, '{r['claim_count']}' Free Qty Claims) "
                    f"'{dummy.name}' (placeholder) ko transfer ho gaya hai. "
                    f"Jab naya Employee mile, 'Transfer Data' screen se '{dummy.name}' ko select karke "
                    f"naye employee ko sab transfer kar dena."
                )

                # 🌟 Audit Log: Resign hote waqt Old Employee -> Dummy transfer ka record
                EmployeeTransferLog.objects.create(
                    transferred_by=request.user.employee,
                    old_employee_name=old_emp.name,
                    new_employee=dummy,
                    details=(
                        f"[RESIGN -> VACANT] Reason:{reason}, "
                        f"Doctors:{r['doc_count']}, Chemists:{r['chem_count']}, "
                        f"Team:{r['team_count']}, SaleReports:{r['sale_count']}, "
                        f"GiftPlans:{r['gift_count']}, FreeQtyClaims:{r['claim_count']} "
                        f"(skipped:{r['claim_skipped']})"
                    ),
                )

        except Exception as e:
            messages.error(request, f"❌ Resign process fail ho gaya: {str(e)}")

        return redirect('resign_employee')

    return render(request, 'resign_employee.html', {'employees': resignable_employees})
