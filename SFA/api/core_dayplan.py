"""
SFA/api/core_dayplan.py
========================
Day Start / Day End workflow — dashboard, day-start, day-end, expense calc.
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

# 🌟 FIX: api_day_start compliance-check ke liye ye 2 helpers chahiye,
# jo core_misc.py me define hain (NameError aa raha tha kyunki
# wildcard import underscore-prefixed names ko skip kar deta hai)
from .core_misc import _get_compliance_block, _get_compliance_alerts

@api_view(['GET', 'POST']) 
@permission_classes([IsAuthenticated])
def api_dashboard(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    sync_dcr_calendar(employee)
    open_day, stuck_day = get_open_day(employee)
    today = timezone.localdate()

    # 🌟 FIX: Extra Route Add Logic
    if request.method == 'POST' and open_day:
        extra_route_id = request.data.get('extra_route_id')
        if extra_route_id:
            open_day.routes.add(extra_route_id)
            return Response({'message': 'Extra Route successfully add ho gaya!'})
        return Response({'error': 'Route ID missing hai'}, status=400)

    oldest_pending_status = DailyDCRStatus.objects.filter(
        employee=employee, is_open=True, is_submitted=False
    ).order_by('date').first()

    if open_day:
        working_date = open_day.date
    elif oldest_pending_status:
        working_date = oldest_pending_status.date
    else:
        working_date = today

    # 🌟 THE ULTIMATE BACKEND FIX: App aur Database ka state sync karna
    actual_day_start = DayStart.objects.filter(employee=employee, date=working_date).first()
    if actual_day_start:
        open_day = actual_day_start
        is_day_started = True
    else:
        is_day_started = False
    is_day_ended = DayEnd.objects.filter(
        employee=employee, date=working_date, is_closed=True
    ).exists()

    today_stats = {'dr_visits': 0, 'chem_visits': 0, 'samples': 0, 'pob': 0.0}
    active_routes = []
    pending_doctors = []
    pending_chemists = []

    if is_day_started:
        active_routes = [{'id': r.id, 'name': r.name, 'category': r.category} for r in open_day.routes.all()]

        if open_day.work_type == 'Field Work':
            daily_dcr = DailyDCR.objects.prefetch_related('visits__doctor', 'visits__chemist').filter(employee=employee, date=working_date).first()
            visited_doc_ids, visited_chem_ids = set(), set()
            
            if daily_dcr:
                all_visits = list(daily_dcr.visits.all())
                dr_visits = [v for v in all_visits if v.doctor]
                ch_visits = [v for v in all_visits if v.chemist]
                visited_doc_ids = {v.doctor_id for v in dr_visits}
                visited_chem_ids = {v.chemist_id for v in ch_visits}
                today_stats['dr_visits'] = len(dr_visits)
                today_stats['chem_visits'] = len(ch_visits)

                agg = DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).aggregate(s=Sum('sample_qty'))
                today_stats['samples'] = agg['s'] or 0

                for d in DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).select_related('product'):
                    price = float(d.product.price) if getattr(d.product, 'price', None) else 0.0
                    today_stats['pob'] += (d.order_qty or 0) * price
                today_stats['pob'] = round(today_stats['pob'], 2)

            team_employees = get_full_team_employees(employee)
            route_objs = open_day.routes.all()

            pending_doctors = [
                {'id': d.id, 'name': d.name, 'route': d.route.name if d.route else None}
                for d in Doctor.objects.select_related('route').filter(
                    allocated_to__in=team_employees, route__in=route_objs, status='Approved'
                ) if d.id not in visited_doc_ids
            ]
            pending_chemists = [
                {'id': c.id, 'name': c.name, 'route': c.route.name if c.route else None}
                for c in Chemist.objects.select_related('route').filter(
                    allocated_to__in=team_employees, route__in=route_objs, status='Approved'
                ) if c.id not in visited_chem_ids
            ]

    notices = [{'title': n.title, 'body': n.body, 'date': str(n.created_at.date()) if n.created_at else None} for n in CompanyNotice.objects.filter(company=employee.company, is_active=True).order_by('-created_at')[:5]]  # 🌟 FIX: company-scoped

    return Response({
        'employee': {'id': employee.id, 'name': employee.name, 'designation': employee.designation, 'hq': employee.headquarter.name if employee.headquarter else None},
        'today': str(today),
        'dcr': {
            'is_day_started': is_day_started, 'is_day_ended': is_day_ended, 'working_date': str(working_date),
            'work_type': open_day.work_type if open_day else None, 'active_routes': active_routes,
            # 🌟 FIX: Safe check lagaya taaki agar created_at field na ho toh server crash na ho
            'start_time': open_day.created_at.isoformat() if open_day and hasattr(open_day, 'created_at') and open_day.created_at else None,
        },
        'today_stats': today_stats,
        'pending': {'doctors': pending_doctors, 'chemists': pending_chemists},
        'notices': notices,
        'stuck_day': str(stuck_day.date) if stuck_day else None,
    })

# ==============================================================================
# 🌅 DAY START
# ==============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_day_start(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile is missing.'}, status=400)

    sync_dcr_calendar(employee)
    today = timezone.localdate()
    setting = SystemSetting.objects.filter(company=employee.company).first()


    # 1. Auto-resolve pending open days (Leave/Holiday/Sunday)
    oldest_open = None
    for dcr in DailyDCRStatus.objects.filter(employee=employee, is_open=True, is_submitted=False).order_by('date'):
        is_leave = LeaveApplication.objects.filter(employee=employee, status='Approved', start_date__lte=dcr.date, end_date__gte=dcr.date).exists()
        is_holiday = Holiday.objects.filter(company=employee.company, date=dcr.date, status='Approved').exists()  # 🌟 FIX: company-scoped

        if is_leave or is_holiday or dcr.date.weekday() == 6:
            dcr.is_open = False
            dcr.day_type = 'Leave' if is_leave else ('Holiday' if is_holiday else 'Sunday')
            dcr.save()
        else:
            oldest_open = dcr
            break

    # 2. Determine target working date safely for both GET and POST
    working_date = oldest_open.date if oldest_open else today
    
    if request.method == 'GET':
        date_str = request.GET.get('date')
    else:
        date_str = request.data.get('date')
        if not date_str:
            return Response({'error': 'Date field is required.'}, status=400)

    if date_str:
        try: 
            working_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError: 
            return Response({'error': 'Invalid date format. Expected YYYY-MM-DD.'}, status=400)

    # ==============================================================================
    # 🛑 THE GATEKEEPERS (Checks run before GET and POST to block form rendering)
    # ==============================================================================

    # A0. 🌟 CALENDAR STATUS CHECK (Sunday/Holiday/Leave lock — same as web day_start_view)
    dcr_status = DailyDCRStatus.objects.filter(employee=employee, date=working_date).first()
    if dcr_status and not dcr_status.is_open:
        if dcr_status.is_submitted:
            return Response({'error': f'Day End has already been submitted for {working_date}.'}, status=403)
        return Response({
            'error': f'{working_date} is locked ({dcr_status.day_type or "blocked"}). Aap is date par Day Start nahi kar sakte.'
        }, status=403)

    # A. Day Already Closed Check
    if DayEnd.objects.filter(employee=employee, date=working_date, is_closed=True).exists():
        return Response({'error': f'Day End has already been submitted for {working_date}.'}, status=403)
    if DayStart.objects.filter(employee=employee, date=working_date).exists():
    	return Response({'error': f'Day is already started for {working_date}...'}, status=403)
    # B. Sequence Check
    if oldest_open and working_date > oldest_open.date:
        return Response({'error': f'Sequence blocked. Please submit the Day End for {oldest_open.date} first.', 'pending_date': str(oldest_open.date)}, status=403)

    # C. Approved Leave Check
    if LeaveApplication.objects.filter(employee=employee, status='Approved', start_date__lte=working_date, end_date__gte=working_date).exists():
        return Response({'error': f'You have an approved leave for {working_date}.'}, status=403)

    # D. Compliance Hard Block (Missing MTP or Pending Approvals)
    compliance_error = _get_compliance_block(employee, today, setting)
    if compliance_error: 
        return Response({'error': compliance_error}, status=403)

    # ==============================================================================
    # ✅ GET REQUEST: Send form data only if all gatekeepers pass
    # ==============================================================================
    if request.method == 'GET':
        alerts = _get_compliance_alerts(employee, today, setting)
        team_employees = Employee.objects.filter(id=employee.id) if employee.designation == 'MR' else get_full_team_employees(employee)

        all_terr_ids = get_team_territory_ids(team_employees)
        all_route_ids = get_team_route_ids(team_employees, all_terr_ids, approved_only=True, include_tour_plan=True)

        yesterday_ds = DayStart.objects.filter(employee=employee, date=working_date - timedelta(days=1), night_stay=True).first()
        suggested_route = DailyTourPlan.objects.filter(mtp__employee=employee, date=working_date, mtp__status='Approved').select_related('route').first()

        subordinates = list(team_employees.exclude(id=employee.id))
        superiors = employee.get_my_managers()
        joint_employees = [{'id': e.id, 'name': e.name, 'designation': e.designation} for e in subordinates + superiors]

        return Response({
            'working_date': str(working_date), 
            'my_hq_id': employee.headquarter_id,
            'oldest_pending_date': str(oldest_open.date) if oldest_open else None,
            'alerts': alerts, 
            'is_return_day': yesterday_ds is not None,
            'territories': [{'id': t.id, 'name': t.name} for t in Territory.objects.filter(id__in=all_terr_ids).order_by('name')],
            'routes': [{
                'id': r.id, 
                'name': r.name, 
                'category': r.category, 
                'territory': r.territory.name if r.territory else None,
                'territory_id': r.territory.id if r.territory else None
            } for r in Route.objects.filter(id__in=all_route_ids).select_related('territory').order_by('category', 'name')],
            'suggested_route': {'id': suggested_route.route.id, 'name': suggested_route.route.name} if suggested_route and suggested_route.route else None,
            'joint_employees': joint_employees,
        })

    # ==============================================================================
    # 📤 POST REQUEST: Process Day Start Data
    # ==============================================================================
    if request.method == 'POST':
        try:
            joint_emp = Employee.objects.filter(id=request.data.get('joint_with_id')).first() if request.data.get('joint_with_id') else None

            day_start, created = DayStart.objects.get_or_create(
                employee=employee, date=working_date,
                defaults={
                    'territory_id': request.data.get('territory_id') or None,
                    'night_stay': bool(request.data.get('night_stay', False)),
                    'latitude': request.data.get('latitude') or None, 
                    'longitude': request.data.get('longitude') or None,
                    'work_type': request.data.get('work_type', 'Field Work'), 
                    'joint_worked_with': joint_emp,
                }
            )

            if created:
                route_id = request.data.get('route_id')
                if route_id and request.data.get('work_type', 'Field Work') == 'Field Work': 
                    day_start.routes.add(route_id)
                return Response({'message': f'Day Start submitted successfully for {working_date}.', 'date': str(working_date)})
            else:
                return Response({'error': f'Day Start already exists for {working_date}.'}, status=400)

        except Exception as e:
            return Response({'error': str(e)}, status=500)

# ==============================================================================
# 🌟 STANDALONE EXPENSE ENGINE
# ==============================================================================
def calculate_expense(emp, ds_obj):
    NO_EXPENSE_WORK_TYPES = ['Strike', 'Holiday', 'Leave']
    if ds_obj.work_type in NO_EXPENSE_WORK_TYPES:
        return {'da': 0, 'ta': 0, 'distance': 0, 'territory_category': 'HQ', 'night_stay': ds_obj.night_stay, 'is_slab3': False}

    routes = ds_obj.routes.select_related('territory').all()
    night_stay = ds_obj.night_stay

    yesterday_ds = DayStart.objects.filter(employee=emp, date=ds_obj.date - timedelta(days=1)).first()
    is_prev_night_stay = yesterday_ds.night_stay if yesterday_ds else False
    is_return_day = is_prev_night_stay and not night_stay

    start_hq = yesterday_ds.territory if (is_prev_night_stay and yesterday_ds.territory) else emp.headquarter

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
        da_rate = DARate.objects.get(designation=emp.designation)
        da = {'HQ': da_rate.hq_da, 'EX_HQ': da_rate.exhq_da, 'OUTSTATION': da_rate.outstation_da}[eff_cat]
    except DARate.DoesNotExist: da = 0

    if not routes.exists() or eff_cat == 'HQ':
        return {'da': round(float(da), 2), 'ta': 0, 'distance': 0, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}

    changed_city_today = any(r.territory != start_hq for r in routes) if start_hq else False

    if is_return_day or (eff_cat == 'OUTSTATION' and night_stay and not is_prev_night_stay): transit_multiplier = 1
    elif eff_cat == 'OUTSTATION' and night_stay and is_prev_night_stay: transit_multiplier = 1 if changed_city_today else 0
    else: transit_multiplier = 2

    billed_distance = (best_local * 2) + (best_transit * transit_multiplier)

    try:
        ta_rate = TARate.objects.get(designation=emp.designation)
        if billed_distance == 0: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
        elif distance <= ta_rate.slab1_upto_km: ta = round(billed_distance * float(ta_rate.slab1_rate), 2)
        elif distance <= ta_rate.slab2_upto_km: ta = round(billed_distance * float(ta_rate.slab2_rate), 2)
        else: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': True}
        return {'da': round(float(da), 2), 'ta': ta, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}
    except TARate.DoesNotExist: return {'da': round(float(da), 2), 'ta': 0, 'distance': distance, 'territory_category': eff_cat, 'night_stay': night_stay, 'is_slab3': False}

# ==============================================================================
# 🌇 DAY END
# ==============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_day_end(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile is missing.'}, status=400)

    open_day, stuck_day = get_open_day(employee)

    # 🌟 NAYA FIX: Day End mein bhi DayStart object ko manually fetch karna
    if not open_day:
        old_pend = DailyDCRStatus.objects.filter(employee=employee, is_open=True, is_submitted=False).order_by('date').first()
        wd = old_pend.date if old_pend else timezone.localdate()
        open_day = DayStart.objects.filter(employee=employee, date=wd).first()

    if stuck_day:
        return Response({
            'error': f'Pending Day Start for {stuck_day.date} is locked. Please contact the administrator.', 
            'stuck_date': str(stuck_day.date)
        }, status=400)

    if not open_day:
        return Response({'error': 'Please start your day before attempting to close it.'}, status=400)

    working_date = open_day.date
    day_closed = DayEnd.objects.filter(employee=employee, date=working_date, is_closed=True).exists()

    if request.method == 'GET':
        daily_dcr = DailyDCR.objects.filter(employee=employee, date=working_date).first()
        dr_count, ch_count, samples, pob = 0, 0, 0, 0.0
        dr_visits_data, ch_visits_data = [], []
        
        if daily_dcr:
            visits = daily_dcr.visits.all()
            dr_visits = visits.filter(doctor__isnull=False).select_related('doctor')
            ch_visits = visits.filter(chemist__isnull=False).select_related('chemist')
            dr_count = dr_visits.count()
            ch_count = ch_visits.count()
            agg = DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).aggregate(s=Sum('sample_qty'))
            samples = agg['s'] or 0
            for d in DCRProductDetail.objects.filter(visit__daily_dcr=daily_dcr).select_related('product'):
                price = float(d.product.price) if getattr(d.product, 'price', None) else 0.0
                pob += (d.order_qty or 0) * price

            # 🌟 Visits with IST timestamps for Flutter
            dr_visits_data = [
                {'id': v.id, 'doctor': {'name': v.doctor.name}, 'created_at': v.created_at.isoformat() if v.created_at else None}
                for v in dr_visits
            ]
            ch_visits_data = [
                {'id': v.id, 'chemist': {'name': v.chemist.name}, 'created_at': v.created_at.isoformat() if v.created_at else None}
                for v in ch_visits
            ]

        expense_preview = None
        if not day_closed:
            expense_preview = calculate_expense(employee, open_day)

        return Response({
            'working_date': str(working_date), 'is_already_closed': day_closed, 'work_type': open_day.work_type,
            # 🌟 FIX: Safe check lagaya taaki crash na ho
            'day_start_time': open_day.created_at.isoformat() if hasattr(open_day, 'created_at') and open_day.created_at else None,
            'today_stats': {'dr_visits': dr_count, 'chem_visits': ch_count, 'samples': samples, 'pob': round(pob, 2)},
            'dr_visits': dr_visits_data,   # 🌟 Timestamps ke saath
            'chem_visits': ch_visits_data, # 🌟 Timestamps ke saath
            'expense_preview': expense_preview 
        })

    if day_closed:
        return Response({'error': f'Day End has already been submitted for {working_date}.'}, status=400)

    try:
        data = request.data
        # Handle boolean strings from multipart/form-data
        night_stay_str = str(data.get('night_stay', '')).lower()
        night_stay = night_stay_str in ['true', '1'] 
        
        day_end, created = DayEnd.objects.get_or_create(
            employee=employee, date=working_date,
            defaults={'is_closed': True, 'latitude': data.get('latitude') or None, 'longitude': data.get('longitude') or None}
        )
        if not created:
            day_end.is_closed = True
            day_end.save()

        DailyDCRStatus.objects.filter(employee=employee, date=working_date).update(is_open=False, is_submitted=True)

        exp_prev = calculate_expense(employee, open_day)
        master, _ = MonthlyExpenseReport.objects.get_or_create(employee=employee, month=working_date.month, year=working_date.year, defaults={'status': 'Draft'})

        actual_fare = float(data.get('actual_fare') or 0.0) if exp_prev['is_slab3'] else 0.0
        final_ta = actual_fare if exp_prev['is_slab3'] else exp_prev['ta']
        
        # Get the uploaded image file
        misc_bill_file = request.FILES.get('misc_bill')

        expense_defaults = {
            'monthly_report': master, 
            'territory_category': exp_prev['territory_category'],
            'night_stay': night_stay, 
            'distance_km': exp_prev['distance'],
            'da_amount': exp_prev['da'], 
            'ta_amount': final_ta, 
            'is_slab3': exp_prev['is_slab3'],
            'actual_fare': actual_fare, 
            'misc_amount': float(data.get('misc_amount') or 0.0)
        }
        
        # Only update the image if a new one is provided
        if misc_bill_file:
            expense_defaults['misc_bill'] = misc_bill_file

        DailyExpense.objects.update_or_create(
            employee=employee, date=working_date, 
            defaults=expense_defaults
        )
        
        return Response({'message': f'Day closed successfully for {working_date}. Expenses have been generated.', 'date': str(working_date)})

    except Exception as e:
        return Response({'error': str(e)}, status=500)

# ==============================================================================
# 🗑️ DELETE VISIT
# ==============================================================================

