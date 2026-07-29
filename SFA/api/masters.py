"""
SFA/api/masters.py
==================
Flutter ke liye Masters REST API — Doctors, Chemists, Routes, Leaves, Gifts etc.
"""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import datetime

# 🌟 SARE MODELS EK HI JAGAH IMPORT KAR LIYE
from SFA.models import (
    Employee, Doctor, Chemist, Route, Territory,
    DoctorEditRequest, ChemistEditRequest,
    LeaveBalance, LeaveApplication, MRInventory, 
    GiftCampaignPlan, PromoItem, Holiday, DoctorChemistProductMapping
)
from SFA.services.team import (
    get_full_team_employees,
    get_team_territory_ids,
    get_team_requested_routes,
    get_dropdown_team,
)
from SFA.company_helpers import (
    get_doctors, get_chemists, get_territories, get_routes, get_holidays,
)


# ==============================================================================
# 🩺 DOCTORS
# ==============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_doctors(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)

    # ── GET ──
    if request.method == 'GET':
        emp_id = request.GET.get('employee_id', str(employee.id))
        try:
            selected_emp = Employee.objects.get(id=emp_id)
        except Employee.DoesNotExist:
            selected_emp = employee

        if not team_employees.filter(id=selected_emp.id).exists():
            return Response({'error': 'Access denied'}, status=403)

        doc_status = request.GET.get('status', 'Approved')
        qs = get_doctors(
            employee.company, allocated_to=selected_emp, status=doc_status
        ).select_related('route', 'territory')

        route_id = request.GET.get('route_id')
        if route_id:
            qs = qs.filter(route_id=route_id)

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

        today = timezone.localdate()
        return Response([_doctor_dict(d, today) for d in qs.order_by('name')])

    # ── POST: Add Doctor ──
    if request.method == 'POST':
        data = request.data
        files = request.FILES
        
        name = (data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Doctor name required hai'}, status=400)

        allocated_id = data.get('allocated_to_id')
        if allocated_id and employee.designation != 'MR':
            allocated_emp = get_object_or_404(Employee, id=allocated_id, company=employee.company)
            if not team_employees.filter(id=allocated_emp.id).exists():
                return Response({'error': 'Access denied — ye employee tumhari team mein nahi hai'}, status=403)
        else:
            allocated_emp = employee

        territory_id = data.get('territory') or data.get('territory_id') or None
        route_id = data.get('route') or data.get('route_id') or None

        if territory_id:
            get_object_or_404(Territory, id=territory_id, company=employee.company)
        if route_id:
            get_object_or_404(Route, id=route_id, company=employee.company)

        try:
            doctor = Doctor(
                company=allocated_emp.company,
                name=name,
                specialty=(data.get('specialty') or '').strip() or None,
                territory_id=territory_id,
                route_id=route_id,
                allocated_to=allocated_emp,
                address=(data.get('address') or '').strip() or None,
                residential_address=(data.get('residential_address') or '').strip() or None,
                mobile=(data.get('mobile') or '').strip() or None,
                email=(data.get('email') or '').strip() or None,
                degree=(data.get('degree') or '').strip() or None,
                category=(data.get('category') or '').strip() or None,
                dob=data.get('dob') or None,
                dom=data.get('dom') or None,
                spouse_dob=data.get('spouse_dob') or None,
                child_1_dob=data.get('child_1_dob') or None, 
                child_2_dob=data.get('child_2_dob') or None,
                latitude=data.get('latitude') or None,
                longitude=data.get('longitude') or None,
            )

            if 'photo' in files:
                doctor.photo = files['photo']
            if 'vcard_photo' in files:
                doctor.vcard_photo = files['vcard_photo']

            doctor.save()

            return Response({
                'message': f"Dr. {doctor.name} successfully add ho gaya! (Pending approval)",
                'id': doctor.id,
                'status': doctor.status,
            }, status=201)

        except Exception as e:
            return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_doctor_detail(request, doc_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    doctor = get_object_or_404(
        Doctor.objects.select_related('route', 'territory', 'allocated_to'),
        id=doc_id,
        company=employee.company,
        allocated_to__in=team_employees
    )

    data = _doctor_dict(doctor, timezone.localdate(), full=True)
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_doctor_edit_request(request, doc_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    doc = get_object_or_404(
        Doctor, id=doc_id,
        company=employee.company,
        allocated_to__in=team_employees
    )

    if DoctorEditRequest.objects.filter(doctor=doc, status='Pending').exists():
        return Response(
            {'error': f"Dr. {doc.name} ka edit request pehle se pending hai. Manager approve kare tab naya bhejo."},
            status=400
        )

    data = request.data
    try:
        DoctorEditRequest.objects.create(
            doctor=doc,
            employee=employee,
            req_name=data.get('name') or doc.name,
            req_degree=data.get('degree') or None,
            req_specialty=data.get('specialty') or None,
            req_category=data.get('category') or None,
            req_territory_id=data.get('territory_id') or None,
            req_route_id=data.get('route_id') or None,
            req_mobile=data.get('mobile') or None,
            req_email=data.get('email') or None,
            req_dob=data.get('dob') or None,
            req_address=data.get('address') or None,
            req_dom=data.get('dom') or None,
            req_spouse_dob=data.get('spouse_dob') or None,
            status='Pending'
        )
        return Response({
            'message': f"Dr. {doc.name} ki update request Manager ko bhej di gayi!"
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ==============================================================================
# 🧪 CHEMISTS
# ==============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_chemists(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)

    # ── GET ──
    if request.method == 'GET':
        emp_id = request.GET.get('employee_id', str(employee.id))
        try:
            selected_emp = Employee.objects.get(id=emp_id)
        except Employee.DoesNotExist:
            selected_emp = employee

        if not team_employees.filter(id=selected_emp.id).exists():
            return Response({'error': 'Access denied'}, status=403)

        chem_status = request.GET.get('status', 'Approved')
        qs = get_chemists(
            employee.company, allocated_to=selected_emp, status=chem_status
        ).select_related('route', 'territory')

        route_id = request.GET.get('route_id')
        if route_id:
            qs = qs.filter(route_id=route_id)

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search)

        return Response([_chemist_dict(c) for c in qs.order_by('name')])

    # ── POST: Add Chemist ──
    data = request.data
    files = request.FILES
    name = (data.get('name') or '').strip()
    if not name:
        return Response({'error': 'Chemist name required hai'}, status=400)

    allocated_id = data.get('allocated_to_id')
    if allocated_id and employee.designation != 'MR':
        allocated_emp = get_object_or_404(Employee, id=allocated_id, company=employee.company)
        if not team_employees.filter(id=allocated_emp.id).exists():
            return Response({'error': 'Access denied'}, status=403)
    else:
        allocated_emp = employee

    territory_id = data.get('territory_id') or None
    route_id = data.get('route_id') or None

    if territory_id:
        get_object_or_404(Territory, id=territory_id, company=employee.company)
    if route_id:
        get_object_or_404(Route, id=route_id, company=employee.company)

    try:
        chemist = Chemist(
            company=allocated_emp.company,
            name=name,
            phone=(data.get('phone') or '').strip() or None,
            address=(data.get('address') or '').strip() or None,
            territory_id=territory_id,
            route_id=route_id,
            allocated_to=allocated_emp,
            # 🌟 NAYA: Owner Info & Card Photo
            owner_name=(data.get('owner_name') or '').strip() or None,
            owner_dob=data.get('owner_dob') or None,
        )
        
        if 'card_photo' in files:
            chemist.card_photo = files['card_photo']
            
        chemist.save()
        
        return Response({
            'message': f"{chemist.name} successfully add ho gaya! (Pending approval)",
            'id': chemist.id,
            'status': chemist.status,
        }, status=201)

    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_chemist_detail(request, chem_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    chemist = get_object_or_404(
        Chemist.objects.select_related('route', 'territory', 'allocated_to'),
        id=chem_id,
        company=employee.company,
        allocated_to__in=team_employees
    )

    data = _chemist_dict(chemist, full=True)
    if chemist.allocated_to:
        data['allocated_to'] = {'id': chemist.allocated_to.id, 'name': chemist.allocated_to.name}
        
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_chemist_edit_request(request, chem_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    chem = get_object_or_404(
        Chemist, id=chem_id,
        company=employee.company,
        allocated_to__in=team_employees
    )

    if ChemistEditRequest.objects.filter(chemist=chem, status='Pending').exists():
        return Response(
            {'error': f"{chem.name} ka edit request pehle se pending hai."},
            status=400
        )

    data = request.data
    try:
        ChemistEditRequest.objects.create(
            chemist=chem,
            employee=employee,
            req_name=data.get('name') or chem.name,
            req_phone=data.get('phone') or None,
            req_address=data.get('address') or None,
            req_territory_id=data.get('territory_id') or None,
            req_route_id=data.get('route_id') or None,
            status='Pending'
        )
        return Response({'message': f"{chem.name} ki update request Manager ko bhej di gayi!"})
    except Exception as e:
        return Response({'error': str(e)}, status=500)

# ==============================================================================
# 🗺️ ROUTES & TERRITORIES
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_routes(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    terr_ids = get_team_territory_ids(team_employees)
    routes = get_team_requested_routes(team_employees, terr_ids).filter(
        company=employee.company
    )

    category = request.GET.get('category')
    if category:
        routes = routes.filter(category=category)

    return Response([
        {
            'id': r.id,
            'name': r.name,
            'category': r.category,
            'territory': {'id': r.territory.id, 'name': r.territory.name} if r.territory else None,
            'distance_from_hq': float(r.distance_from_hq) if r.distance_from_hq else None,
        }
        for r in routes
    ])

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_route(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    data = request.data
    name = (data.get('name') or '').strip()
    territory_id = data.get('territory_id')
    category = data.get('category') or 'HQ'
    
    try:
        distance = float(data.get('distance_from_hq') or 0.0)
    except ValueError:
        distance = 0.0

    if not name or not territory_id:
        return Response({'error': 'Route Name and Territory are required'}, status=400)

    try:
        territory = get_object_or_404(Territory, id=territory_id, company=employee.company)

        route = Route.objects.create(
            company=employee.company,
            name=name,
            territory=territory,
            category=category,
            distance_from_hq=distance,
            requested_by=employee,
            status='Pending'
        )
        return Response({
            'message': f"Route '{route.name}' requested successfully!",
            'id': route.id
        }, status=201)

    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_territories(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee, ordered=False)
    terr_ids = get_team_territory_ids(team_employees)
    territories = get_territories(employee.company, id__in=terr_ids).order_by('name')

    return Response([
        {'id': t.id, 'name': t.name, 'city': t.city if hasattr(t, 'city') else None}
        for t in territories
    ])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dropdowns(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_employees = get_dropdown_team(employee)
    terr_ids = get_team_territory_ids(team_employees)
    territories = get_territories(employee.company, id__in=terr_ids).order_by('name')
    routes = get_team_requested_routes(team_employees, terr_ids).filter(
        company=employee.company
    )

    return Response({
        'territories': [
            {'id': t.id, 'name': t.name} for t in territories
        ],
        'routes': [
            {
                'id': r.id,
                'name': r.name,
                'category': r.category,
                'territory': {'id': r.territory.id, 'name': r.territory.name} if r.territory else None,
            }
            for r in routes
        ],
        'team_employees': [
            {'id': e.id, 'name': e.name, 'designation': e.designation}
            for e in team_employees
        ],
    })


# ==============================================================================
# 🔧 PRIVATE HELPERS
# ==============================================================================

def _doctor_dict(doc, today=None, full=False):
    data = {
        'id': doc.id,
        'name': doc.name,
        'specialty': doc.specialty or '',
        'category': doc.category or '',
        'degree': doc.degree or '',
        'mobile': doc.mobile or '',
        'route': {'id': doc.route.id, 'name': doc.route.name} if doc.route else None,
        'territory': {'id': doc.territory.id, 'name': doc.territory.name} if doc.territory else None,
        'status': doc.status,
        'photo_url': doc.photo.url if doc.photo else None,
    }

    if today and doc.dob:
        data['has_birthday_today'] = (doc.dob.month == today.month and doc.dob.day == today.day)
    else:
        data['has_birthday_today'] = False

    if full:
        data.update({
            'email': doc.email or '',
            'address': doc.address or '',
            'dob': str(doc.dob) if doc.dob else None,
            'dom': str(doc.dom) if doc.dom else None,
            'spouse_dob': str(doc.spouse_dob) if doc.spouse_dob else None,
            'latitude': str(doc.latitude) if doc.latitude else None,
            'longitude': str(doc.longitude) if doc.longitude else None,
            'vcard_url': doc.vcard_photo.url if doc.vcard_photo else None,
            'allocated_to': {
                'id': doc.allocated_to.id,
                'name': doc.allocated_to.name,
            } if doc.allocated_to else None,
        })
    return data


def _chemist_dict(chem, full=False):
    data = {
        'id': chem.id,
        'name': chem.name,
        'phone': chem.phone or '',
        'address': chem.address or '',
        'route': {'id': chem.route.id, 'name': chem.route.name} if chem.route else None,
        'territory': {'id': chem.territory.id, 'name': chem.territory.name} if chem.territory else None,
        'status': chem.status,
    }
    
    # 🌟 NAYA: Full details mein Owner info aur Card Photo bhejna
    if full:
        data.update({
            'owner_name': chem.owner_name or '',
            'owner_dob': str(chem.owner_dob) if chem.owner_dob else None,
            'card_photo_url': chem.card_photo.url if chem.card_photo else None,
            'latitude': str(chem.latitude) if chem.latitude else None,
            'longitude': str(chem.longitude) if chem.longitude else None,
        })
        
    return data


# ==============================================================================
# 🏖️ LEAVES, HOLIDAYS, GIFTS, MAPPINGS
# ==============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_leaves(request):
    employee = request.user.employee
    current_year = timezone.localdate().year


    if request.method == 'GET':
        balance, _ = LeaveBalance.objects.get_or_create(employee=employee, year=current_year)
        applications = LeaveApplication.objects.filter(employee=employee).order_by('-applied_on')
        app_data = []
        for app in applications:
            app_data.append({
                'id': app.id,
                'leave_type': app.get_leave_type_display() if hasattr(app, 'get_leave_type_display') else app.leave_type,
                'no_of_days': float(app.no_of_days),
                'start_date': app.start_date.strftime('%d %b') if app.start_date else '',
                'end_date': app.end_date.strftime('%d %b %Y') if app.end_date else '',
                'status': app.status,
                'manager_remark': getattr(app, 'manager_remark', '') or '',
                'admin_remark': getattr(app, 'admin_remark', '') or ''
            })
            
        # 🌟 FIX: Dono screens ke liye sab keys bhej rahe hain
        return Response({
            'success': True,
            'balance': {
                # Leave Status Screen ke liye
                'rem_cl': balance.cl_total - balance.cl_used,
                'rem_sl': balance.sl_total - balance.sl_used,
                'rem_pl': balance.pl_total - balance.pl_used,
                'cl_total': balance.cl_total,
                'sl_total': balance.sl_total,
                'pl_total': balance.pl_total,
                # Apply Leave Screen ke liye
                'CL_left': balance.cl_total - balance.cl_used,
                'SL_left': balance.sl_total - balance.sl_used,
                'PL_left': balance.pl_total - balance.pl_used,
            },
            # Leave Status Screen ke liye
            'applications': app_data,
            # Apply Leave Screen ke liye
            'history': app_data
        })    

    if request.method == 'POST':
        l_type = request.data.get('leave_type')
        reason = request.data.get('reason', '')
        
        try:
            s_date = datetime.strptime(request.data.get('start_date'), '%Y-%m-%d').date()
            e_date = datetime.strptime(request.data.get('end_date'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return Response({'success': False, 'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)

        days = (e_date - s_date).days + 1
        if days <= 0:
            return Response({'success': False, 'error': 'End date start date ke baad ki honi chahiye.'}, status=400)

        balance, _ = LeaveBalance.objects.get_or_create(employee=employee, year=current_year)
        rem_cl = balance.cl_total - balance.cl_used
        rem_sl = balance.sl_total - balance.sl_used
        rem_pl = balance.pl_total - balance.pl_used

        is_valid = True
        if l_type == 'CL' and rem_cl < days: is_valid = False
        elif l_type == 'SL' and rem_sl < days: is_valid = False
        elif l_type == 'PL' and rem_pl < days: is_valid = False

        if is_valid or l_type == 'LWP':
            LeaveApplication.objects.create(
                employee=employee, leave_type=l_type, start_date=s_date, end_date=e_date, reason=reason
            )
            return Response({'success': True, 'message': f'{l_type} for {days} day(s) applied successfully!'})
        else:
            return Response({'success': False, 'error': f'Insufficient {l_type} balance!'}, status=400)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_holidays(request):
    employee = request.user.employee
    
    if request.method == 'GET':
        subordinate_rbms = []
        is_rbm = (employee.designation == 'RBM')
        
        if not is_rbm and employee.designation in ['ZBM', 'NSM', 'Admin', 'System Administrator']:
            team = get_full_team_employees(employee)
            rbms = team.filter(designation='RBM', is_active=True).order_by('name')
            subordinate_rbms = [{'id': r.id, 'name': r.name} for r in rbms]
            
        holidays = get_holidays(employee.company, proposed_by=employee).order_by('-date')
        data = [{'id': h.id, 'name': h.name, 'date': h.date.strftime('%Y-%m-%d'), 'status': h.status} for h in holidays]
        
        return Response({
            'success': True, 
            'holidays': data,
            'is_rbm': is_rbm,
            'subordinate_rbms': subordinate_rbms
        })

    if request.method == 'POST':
        name = request.data.get('name')
        h_date = request.data.get('date')
        is_national = request.data.get('is_national', False)
        rbm_ids = request.data.get('rbm_ids', [])
        
        if not name or not h_date:
            return Response({'success': False, 'error': 'Name aur Date zaroori hai.'}, status=400)

        status_val = 'Approved' if employee.designation in ['Admin', 'System Administrator'] else 'Pending'

        if employee.designation == 'RBM':
            Holiday.objects.get_or_create(
                company=employee.company, date=h_date, proposed_by=employee,
                defaults={'name': name, 'status': status_val}
            )
        else:
            if is_national:
                Holiday.objects.get_or_create(
                    company=employee.company, date=h_date, proposed_by=employee,
                    defaults={'name': name, 'status': status_val}
                )
            else:
                if not rbm_ids:
                    return Response({'success': False, 'error': 'Please select at least one RBM or mark as National.'}, status=400)
                for r_id in rbm_ids:
                    rbm_emp = get_object_or_404(Employee, id=r_id, company=employee.company)
                    Holiday.objects.get_or_create(
                        company=employee.company, date=h_date, proposed_by=rbm_emp,
                        defaults={'name': name, 'status': status_val}
                    )

        return Response({'success': True, 'message': 'Holiday proposal submitted successfully!'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_doctor_chemists(request, doc_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    get_object_or_404(Doctor, id=doc_id, company=employee.company)

    chemists = [
        {'id': m.chemist.id, 'name': m.chemist.name}
        for m in DoctorChemistProductMapping.objects.filter(
            doctor_id=doc_id
        ).select_related('chemist')
    ]
    seen = set()
    unique_chemists = [c for c in chemists if c['id'] not in seen and not seen.add(c['id'])]
    return Response({'success': True, 'chemists': unique_chemists})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dr_chemist_products(request, doc_id, chem_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    get_object_or_404(Doctor, id=doc_id, company=employee.company)
    get_object_or_404(Chemist, id=chem_id, company=employee.company)

    products = [
        {'id': m.product.id, 'name': m.product.name}
        for m in DoctorChemistProductMapping.objects.filter(
            doctor_id=doc_id, chemist_id=chem_id
        ).select_related('product')
    ]
    return Response({'success': True, 'products': products})