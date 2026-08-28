"""
SFA/api/sales.py
================
Sales & Visit REST API endpoints for Flutter.
"""
from datetime import datetime, date
import calendar
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from SFA.models import (
    Employee, Doctor, Chemist, Product, Stockist,
    DailyDCR, DCRVisit, DCRProductDetail,
    DayEnd, MRInventory, GiftCampaignPlan, DoctorROILedger,
    PartyWiseSaleReport, PartyWiseSaleLine, PrimarySale,
    SystemSetting, MonthlyTargetMaster, TerritoryTarget,
    DoctorRxMapping
)
from SFA.services.team import get_dropdown_team
from SFA.views.core import get_open_day

# ==============================================================================
# 🩺 DOCTOR VISIT
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_doctor_visit_form(request, doc_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        return Response({
            'error': f'Previous Day Start for {stuck_day.date} is locked. Please contact the administrator.',
            'stuck_date': str(stuck_day.date),
        }, status=400)

    if not open_day:
        return Response({'error': 'Please submit your Day Start first.'}, status=400)

    doctor = get_object_or_404(Doctor, id=doc_id, company=employee.company)
    today = open_day.date

    my_inventory = MRInventory.objects.filter(employee=employee, stock_qty__gt=0).select_related('item', 'item__linked_product')

    sample_stock_map = {
        inv.item.linked_product_id: inv.stock_qty
        for inv in my_inventory
        if inv.item.item_type == 'Sample' and inv.item.linked_product_id
    }

    products = [
        {
            'id': p.id,
            'name': p.name,
            'sample_stock': sample_stock_map.get(p.id, 0),
            'order_qty': 0,
        }
        for p in Product.objects.filter(company=employee.company).order_by('name')
    ]

    approved_gift_ids = set(GiftCampaignPlan.objects.filter(
        employee=employee, doctor=doctor,
        status='Approved', month=today.month, year=today.year
    ).values_list('item_id', flat=True))

    gifts = []
    for inv in my_inventory:
        if inv.item.item_type == 'Sample':
            continue
        if inv.item.item_type == 'HighValue' and inv.item.id not in approved_gift_ids:
            continue
        gifts.append({
            'inventory_id': inv.id,
            'item_id': inv.item.id,
            'item_name': inv.item.name,
            'item_type': inv.item.item_type,
            'stock_qty': inv.stock_qty,
            'price': float(inv.item.price) if inv.item.price else 0.0,
        })

    return Response({
        'doctor': {
            'id': doctor.id,
            'name': doctor.name,
            'specialty': doctor.specialty or '',
            'category': doctor.category or '',
            'route': doctor.route.name if doctor.route else None,
        },
        'working_date': str(today),
        'products': products,
        'gifts': gifts,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_doctor_visit_submit(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        return Response({'error': 'Previous Day Start is locked. Please contact the administrator.'}, status=400)
    if not open_day:
        return Response({'error': 'Please submit your Day Start first.'}, status=400)

    data = request.data
    doctor_id = data.get('doctor_id')
    if not doctor_id:
        return Response({'error': 'doctor_id is required.'}, status=400)

    doctor = get_object_or_404(Doctor, id=doctor_id, company=employee.company)

    setting = SystemSetting.objects.filter(company=employee.company).first()
    is_backdated = open_day.date < timezone.localdate()
    is_bypassed = is_backdated and (not setting or not setting.strict_geofence_for_backdate)

    try:
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=open_day.date)

        visit = DCRVisit.objects.create(
            daily_dcr=daily_dcr,
            route=doctor.route,
            doctor=doctor,
            remark=data.get('remark', ''),
            latitude=data.get('latitude') or None,
            longitude=data.get('longitude') or None,
            geofence_bypassed=is_bypassed,
        )

        for prod_data in (data.get('products') or []):
            p_id = prod_data.get('product_id')
            is_det = bool(prod_data.get('is_detailed', False))
            sq = int(prod_data.get('sample_qty') or 0)
            oq = int(prod_data.get('order_qty') or 0)

            if is_det or sq > 0 or oq > 0:
                DCRProductDetail.objects.create(visit=visit, product_id=p_id, is_detailed=is_det, sample_qty=sq, order_qty=oq)
                if sq > 0:
                    sample_inv = MRInventory.objects.filter(employee=employee, item__linked_product_id=p_id, item__item_type='Sample').first()
                    if sample_inv and sample_inv.stock_qty >= sq:
                        sample_inv.stock_qty -= sq
                        sample_inv.save()

        for gift_data in (data.get('gifts') or []):
            item_id = gift_data.get('item_id')
            qty_given = int(gift_data.get('qty') or 0)
            if qty_given > 0:
                try:
                    inventory = MRInventory.objects.get(employee=employee, item_id=item_id)
                    if inventory.stock_qty >= qty_given:
                        inventory.stock_qty -= qty_given
                        inventory.save()
                        DoctorROILedger.objects.create(
                            date_given=open_day.date, doctor=doctor, employee=employee,
                            item=inventory.item, quantity=qty_given,
                            total_value=float(inventory.item.price) * qty_given, visit=visit,
                        )
                except MRInventory.DoesNotExist:
                    pass

        return Response({'message': f'Visit for Dr. {doctor.name} has been saved successfully!', 'visit_id': visit.id}, status=201)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ==============================================================================
# 🧪 CHEMIST VISIT
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_chemist_visit_submit(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    open_day, stuck_day = get_open_day(employee)

    if stuck_day:
        return Response({'error': 'Previous Day Start is locked. Please contact the administrator.'}, status=400)
    if not open_day:
        return Response({'error': 'Please submit your Day Start first.'}, status=400)

    data = request.data
    chemist_id = data.get('chemist_id')
    if not chemist_id:
        return Response({'error': 'chemist_id is required.'}, status=400)

    chemist = get_object_or_404(Chemist, id=chemist_id, company=employee.company)

    try:
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=open_day.date)

        visit = DCRVisit.objects.create(
            daily_dcr=daily_dcr, route=chemist.route, chemist=chemist,
            latitude=data.get('latitude') or None, longitude=data.get('longitude') or None,
        )

        for prod_data in (data.get('products') or []):
            oq = int(prod_data.get('order_qty') or 0)
            if oq > 0:
                DCRProductDetail.objects.create(visit=visit, product_id=prod_data.get('product_id'), sample_qty=0, order_qty=oq)

        return Response({'message': f'Visit for {chemist.name} has been saved successfully!', 'visit_id': visit.id}, status=201)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_today_visits(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    # 🌟 FIX: If 'date' query param is provided, use that specific date
    # regardless of whether the day is already closed.
    date_param = request.query_params.get('date')

    if date_param:
        try:
            working_date = datetime.strptime(date_param, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Expected YYYY-MM-DD.'}, status=400)
    else:
        open_day, _ = get_open_day(employee)
        if not open_day:
            return Response({
                'working_date': str(timezone.localdate()),
                'doctor_visits': [], 'chemist_visits': [],
                'summary': {'dr_count': 0, 'chem_count': 0, 'total_samples': 0, 'total_pob': 0.0}
            })
        working_date = open_day.date

    daily_dcr = DailyDCR.objects.filter(employee=employee, date=working_date).first()

    if not daily_dcr:
        return Response({
            'working_date': str(working_date),
            'doctor_visits': [], 'chemist_visits': [],
            'summary': {'dr_count': 0, 'chem_count': 0, 'total_samples': 0, 'total_pob': 0.0}
        })

    # 🌟 FIX: Ensure the latest visits appear at the top to match Optimistic UI updates
    all_visits = daily_dcr.visits.select_related('doctor', 'chemist', 'route').prefetch_related('product_details__product').all().order_by('-created_at')

    doctor_visits = []
    chemist_visits = []
    total_samples = 0
    total_pob = 0.0

    for v in all_visits:
        product_details = list(v.product_details.all())

        if v.doctor:
            detailed = [pd.product.name for pd in product_details if pd.is_detailed]
            samples = sum(pd.sample_qty or 0 for pd in product_details)
            pob = sum((pd.order_qty or 0) * (float(pd.product.price) if getattr(pd.product, 'price', None) else 0.0) for pd in product_details)
            total_samples += samples
            total_pob += pob

            doctor_visits.append({
                'id': v.id,
                'doctor': {'id': v.doctor.id, 'name': v.doctor.name, 'specialty': v.doctor.specialty or '', 'category': v.doctor.category or ''},
                'route': v.route.name if v.route else None,
                'remark': v.remark or '',
                'time': v.created_at.strftime('%I:%M %p') if hasattr(v, 'created_at') and v.created_at else None,
                'products_detailed': detailed, 'samples_given': samples, 'pob': round(pob, 2),
                'visit_lat': str(v.latitude) if v.latitude else None,
                'visit_lng': str(v.longitude) if v.longitude else None,
                'target_lat': str(v.doctor.latitude) if v.doctor.latitude else None,
                'target_lng': str(v.doctor.longitude) if v.doctor.longitude else None,
            })

        elif v.chemist:
            ordered = [{'name': pd.product.name, 'qty': pd.order_qty or 0} for pd in product_details if (pd.order_qty or 0) > 0]
            chemist_visits.append({
                'id': v.id,
                'chemist': {'id': v.chemist.id, 'name': v.chemist.name},
                'route': v.route.name if v.route else None,
                'time': v.created_at.strftime('%I:%M %p') if hasattr(v, 'created_at') and v.created_at else None,
                'products_ordered': ordered,
                'visit_lat': str(v.latitude) if v.latitude else None,
                'visit_lng': str(v.longitude) if v.longitude else None,
                'target_lat': str(v.chemist.latitude) if v.chemist.latitude else None,
                'target_lng': str(v.chemist.longitude) if v.chemist.longitude else None,
            })

    return Response({
        'working_date': str(working_date),
        'doctor_visits': doctor_visits, 'chemist_visits': chemist_visits,
        'summary': {'dr_count': len(doctor_visits), 'chem_count': len(chemist_visits), 'total_samples': total_samples, 'total_pob': round(total_pob, 2)}
    })

# ==============================================================================
# 🗑️ DELETE VISIT
# ==============================================================================

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_visit(request, visit_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee)
    visit_date = visit.daily_dcr.date

    if DayEnd.objects.filter(employee=employee, date=visit_date, is_closed=True).exists():
        return Response({'error': 'Day End has already been submitted. The visit cannot be deleted.'}, status=400)

    visit.delete()
    return Response({'message': 'Visit has been deleted successfully!'})


# ==============================================================================
# 📊 PARTY WISE SALE (Optimized for RAM & DB)
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_party_wise_get(request):
    employee = request.user.employee
    today = timezone.now().date()
    current_month, current_year = (12, today.year - 1) if today.month == 1 else (today.month - 1, today.year)
    
    setting = SystemSetting.objects.filter(company=employee.company).first()
    deadline = setting.sale_upload_deadline_day if setting and setting.sale_upload_deadline_day else 4
    is_locked = today.day > deadline

    team_employees = get_dropdown_team(employee).filter(designation='MR', is_active=True)
    is_manager_view = employee.designation != 'MR'
    
    selected_emp_id = request.query_params.get('employee_id')
    if not selected_emp_id:
        selected_emp_id = str(employee.id)
    
    selected_emp = get_object_or_404(Employee, id=selected_emp_id, company=employee.company)

    my_terr_ids = [selected_emp.headquarter_id] if selected_emp.headquarter_id else []
    available_stockists = Stockist.objects.filter(territory_id__in=my_terr_ids).order_by('name')
    
    selected_stockist_id = request.query_params.get('stockist_id')
    if selected_stockist_id and not available_stockists.filter(id=selected_stockist_id).exists():
        selected_stockist_id = None
    if not selected_stockist_id and available_stockists.exists():
        selected_stockist_id = str(available_stockists.first().id)
        
    selected_stockist = available_stockists.filter(id=selected_stockist_id).first()

    balances = []
    if selected_stockist:
        # 🚀 OPTIMIZATION 1: Utilize Database (SQL) Aggregation instead of Python Loops
        
        # 1. Primary Sale Aggregation (All products)
        primary_agg = PrimarySale.objects.filter(
            stockist=selected_stockist, date__lte=today
        ).values('product_id').annotate(
            t_qty=Sum('quantity'), t_free=Sum('free_quantity')
        )
        primary_dict = {item['product_id']: (item['t_qty'] or 0) + (item['t_free'] or 0) for item in primary_agg}

        # 2. Past Secondary Sale Aggregation
        past_party_agg = PartyWiseSaleLine.objects.filter(
            report__stockist=selected_stockist
        ).filter(
            Q(report__year__lt=current_year) | Q(report__year=current_year, report__month__lt=current_month)
        ).values('product_id').annotate(
            tb=Sum('billed_qty'), tf=Sum('free_qty')
        )
        past_sec_dict = {item['product_id']: (item['tb'] or 0) + (item['tf'] or 0) for item in past_party_agg}

        # 3. Current Month Secondary Sale Aggregation
        current_party_agg = PartyWiseSaleLine.objects.filter(
            report__stockist=selected_stockist, report__month=current_month, report__year=current_year
        ).values('product_id').annotate(
            tb=Sum('billed_qty'), tf=Sum('free_qty')
        )
        curr_sec_dict = {item['product_id']: (item['tb'] or 0) + (item['tf'] or 0) for item in current_party_agg}

        # 🚀 Products are fetched via a single DB query and combined in memory (RAM)
        for prod in Product.objects.filter(company=selected_emp.company):
            total_lifetime_primary = primary_dict.get(prod.id, 0)
            total_past_secondary = past_sec_dict.get(prod.id, 0)
            stock_available_for_this_month = total_lifetime_primary - total_past_secondary
            billed_this_month = curr_sec_dict.get(prod.id, 0)
            current_balance = stock_available_for_this_month - billed_this_month
            
            if total_lifetime_primary > 0 or billed_this_month > 0:
                balances.append({
                    'product_id': prod.id, 'product_name': prod.name, 
                    'total_sale': stock_available_for_this_month, 'billed': billed_this_month, 'balance': current_balance
                })

    chemists = Chemist.objects.filter(allocated_to=selected_emp, status='Approved').order_by('name')
    chem_data = [{'id': c.id, 'name': c.name} for c in chemists]
    
    doctors = Doctor.objects.filter(allocated_to=selected_emp, status='Approved').order_by('name')
    doc_data = [{'id': d.id, 'name': f"Dr. {d.name}"} for d in doctors]
    
    all_prods = Product.objects.filter(company=selected_emp.company).order_by('name')
    prod_data = [{'id': p.id, 'name': p.name} for p in all_prods]
    
    stockist_data = [{'id': s.id, 'name': s.name} for s in available_stockists]
    team_data = [{'id': e.id, 'name': e.name} for e in team_employees]

    return Response({
        'is_locked': is_locked, 'deadline_day': deadline,
        'month': current_month, 'year': current_year,
        'is_manager_view': is_manager_view, 'team_employees': team_data, 
        'selected_emp_id': int(selected_emp_id), 'stockists': stockist_data,
        'selected_stockist_id': int(selected_stockist_id) if selected_stockist_id else None,
        'balances': balances, 'chemists': chem_data, 'doctors': doc_data,
        'all_products': prod_data 
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_party_wise_submit(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing.'}, status=400)

    today = timezone.now().date()
    setting = SystemSetting.objects.filter(company=employee.company).first()
    deadline = setting.sale_upload_deadline_day if setting else 4

    if today.day > deadline and employee.designation not in ['Admin', 'NSM']:
        return Response({'error': f'Entry locked! Editing is not permitted after the {deadline}th of the month.'}, status=400)

    data = request.data
    team_employees = get_dropdown_team(employee, ordered=False)

    emp_id = data.get('employee_id', employee.id)
    try:
        selected_emp = Employee.objects.get(id=emp_id, company=employee.company)
    except Employee.DoesNotExist:
        selected_emp = employee

    if not team_employees.filter(id=selected_emp.id).exists():
        return Response({'error': 'Access denied.'}, status=403)

    curr_month = 12 if today.month == 1 else today.month - 1
    curr_year = today.year - 1 if today.month == 1 else today.year

    stockist_id = data.get('stockist_id')
    chemist_id = data.get('chemist_id')
    doctor_id = data.get('doctor_id')
    lines = data.get('lines', [])

    if not stockist_id: return Response({'error': 'Selecting a Stockist is mandatory.'}, status=400)
    if not chemist_id and not doctor_id: return Response({'error': 'Please select at least one Chemist or Doctor.'}, status=400)
    if not lines: return Response({'error': 'No products were added.'}, status=400)

    stockist = get_object_or_404(Stockist, id=stockist_id, company=employee.company)
    
    chemist = None
    if chemist_id:
        chemist = get_object_or_404(Chemist, id=chemist_id, company=employee.company)

    try:
        report, _ = PartyWiseSaleReport.objects.get_or_create(employee=selected_emp, stockist=stockist, month=curr_month, year=curr_year)

        saved = 0
        for line in lines:
            bq = int(line.get('billed_qty') or 0)
            fq = int(line.get('free_qty') or 0)
            if bq > 0 or fq > 0:
                # 1. Create PartyWiseSaleLine (Assign Chemist if available, otherwise null)
                new_line = PartyWiseSaleLine.objects.create(
                    report=report, chemist=chemist, product_id=line.get('product_id'), billed_qty=bq, free_qty=fq
                )
                
                # 2. If Doctor is selected, create DoctorRxMapping
                if doctor_id:
                    DoctorRxMapping.objects.create(
                        party_line=new_line, doctor_id=doctor_id, mapped_billed_qty=bq, mapped_free_qty=fq
                    )
                saved += 1

        if saved == 0:
            return Response({'error': 'All quantities were zero. No records were saved.'}, status=400)

        return Response({'message': f'Sale saved successfully! {saved} product(s) recorded.', 'month': curr_month, 'year': curr_year}, status=201)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ====================================================================
# 🎯 TARGET SETTING API (Optimized Bulk Create)
# ====================================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_target_setting(request):
    employee = request.user.employee
    
    if not employee.headquarter:
        return Response({'success': False, 'error': 'No Territory/Headquarter is assigned to your profile.'}, status=403)
        
    month = int(request.query_params.get('month') or request.data.get('month') or timezone.now().month)
    year = int(request.query_params.get('year') or request.data.get('year') or timezone.now().year)
    
    master, _ = MonthlyTargetMaster.objects.get_or_create(territory=employee.headquarter, month=month, year=year)
    is_readonly = master.status not in ['Draft', 'Rejected']

    if request.method == 'GET':
        existing_targets = {t.product_id: t.target_qty for t in TerritoryTarget.objects.filter(territory=employee.headquarter, month=month, year=year)}
        
        products_data = []
        for p in Product.objects.filter(company=employee.company):
            products_data.append({'product_id': p.id, 'product_name': p.name, 'target_qty': existing_targets.get(p.id, 0)})
            
        return Response({'success': True, 'status': master.status, 'is_readonly': is_readonly, 'manager_remark': master.manager_remark, 'targets': products_data})

    if request.method == 'POST':
        if is_readonly:
            return Response({'success': False, 'error': 'This target has already been submitted and cannot be edited.'}, status=403)
            
        action = request.data.get('action') 
        target_payload = request.data.get('targets', []) 
        
        # 🚀 OPTIMIZATION 2: Replaced update_or_create within a loop with DB Bulk Update/Create
        existing_targets = {t.product_id: t for t in TerritoryTarget.objects.filter(territory=employee.headquarter, month=month, year=year)}
        
        targets_to_create = []
        targets_to_update = []
        p_ids_to_keep = []

        for item in target_payload:
            p_id = item.get('product_id')
            t_qty = int(item.get('target_qty', 0))
            
            if t_qty > 0:
                p_ids_to_keep.append(p_id)
                if p_id in existing_targets:
                    tgt = existing_targets[p_id]
                    if tgt.target_qty != t_qty:
                        tgt.target_qty = t_qty
                        targets_to_update.append(tgt)
                else:
                    targets_to_create.append(TerritoryTarget(
                        territory=employee.headquarter, product_id=p_id, month=month, year=year, target_qty=t_qty
                    ))
                    
        # Update existing, create new, delete zeroes
        if targets_to_update:
            TerritoryTarget.objects.bulk_update(targets_to_update, ['target_qty'])
        if targets_to_create:
            TerritoryTarget.objects.bulk_create(targets_to_create)
            
        # Delete entries from the DB that were not submitted (deleted on UI)
        TerritoryTarget.objects.filter(territory=employee.headquarter, month=month, year=year).exclude(product_id__in=p_ids_to_keep).delete()
                
        if action == 'Submit':
            master.status = 'Pending_Manager'
            master.approved_by_managers = []
            msg = 'Target has been submitted to the Manager for approval!'
        else:
            master.status = 'Draft'
            msg = 'Target draft saved successfully!'
            
        master.save()
        return Response({'success': True, 'message': msg})


# ====================================================================
# 9. GIFT CAMPAIGN API
# ====================================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_gift_campaign(request):
    employee = request.user.employee

    if request.method == 'GET':
        month = int(request.query_params.get('month') or timezone.now().month)
        year = int(request.query_params.get('year') or timezone.now().year)

        stock = MRInventory.objects.filter(employee=employee, item__item_type__in=['HighValue', 'Gift'], stock_qty__gt=0)
        gifts_data = [{'id': s.item.id, 'name': s.item.name, 'stock': s.stock_qty} for s in stock]

        doctors = Doctor.objects.filter(allocated_to=employee, status='Approved').order_by('name')
        doctors_data = [{'id': d.id, 'name': d.name} for d in doctors]

        history = GiftCampaignPlan.objects.filter(employee=employee).order_by('-id')[:20]
        history_data = [
            {'id': h.id, 'doctor_name': h.doctor.name if h.doctor else 'Unknown', 'item_name': h.item.name if h.item else 'Unknown', 'month': h.month, 'year': h.year, 'status': h.status}
            for h in history
        ]

        return Response({'success': True, 'gifts': gifts_data, 'doctors': doctors_data, 'history': history_data})

    if request.method == 'POST':
        item_id = request.data.get('item_id')
        doctor_ids = request.data.get('doctor_ids', []) 
        month = request.data.get('month')
        year = request.data.get('year')

        if not item_id or not doctor_ids:
            return Response({'success': False, 'error': 'Selecting an Item and at least one Doctor is mandatory.'}, status=400)

        inventory = MRInventory.objects.filter(employee=employee, item_id=item_id, stock_qty__gt=0).first()
        if not inventory:
            return Response({'success': False, 'error': 'You do not have stock available for this item.'}, status=400)

        already_allocated = GiftCampaignPlan.objects.filter(employee=employee, item_id=item_id, month=month, year=year, status__in=['Pending', 'Approved']).count()

        new_docs_to_add = []
        for doc_id in doctor_ids:
            already = GiftCampaignPlan.objects.filter(employee=employee, doctor_id=doc_id, item_id=item_id, month=month, year=year, status__in=['Pending', 'Approved']).exists()
            if not already:
                new_docs_to_add.append(doc_id)

        if already_allocated + len(new_docs_to_add) > inventory.stock_qty:
            available_to_assign = inventory.stock_qty - already_allocated
            return Response({'success': False, 'error': f'Stock Limit Exceeded! Total stock for {inventory.item.name} is {inventory.stock_qty} (of which {already_allocated} are already assigned). You can only select {available_to_assign} more.'}, status=400)

        created = 0
        for doc_id in new_docs_to_add:
            doctor = get_object_or_404(Doctor, id=doc_id, company=employee.company)
            GiftCampaignPlan.objects.create(employee=employee, doctor=doctor, item_id=item_id, month=month, year=year, status='Pending')
            created += 1

        if created > 0:
            return Response({'success': True, 'message': f'Campaign for {created} Doctor(s) has been submitted to the Manager!'})
        else:
            return Response({'success': False, 'error': 'All selected doctors are already included in the plan for this month.'}, status=400)