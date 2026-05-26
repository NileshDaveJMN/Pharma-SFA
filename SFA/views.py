from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# NAYA DATABASE STRUCTURE IMPORT
from .models import (
    Doctor, Chemist, DayEnd, DayStart, Product, Route, 
    DailyDCR, DCRVisit, DCRProductDetail, 
    MonthlyTourProgram, DailyTourPlan, Territory
)
from .serializers import DoctorSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def doctor_list_api(request):
    user = request.user
    try:
        employee = user.employee 
        doctors = Doctor.objects.filter(allocated_to=employee)
        serializer = DoctorSerializer(doctors, many=True)
        return Response(serializer.data)
    except AttributeError:
        return Response({"error": "Is User ke sath koi Employee linked nahi hai"}, status=400)
        
def login_view(request):
    if request.method == "POST":
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(username=u, password=p)
        if user:
            login(request, user)
            return redirect('mr_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Invalid Credentials'})
    return render(request, 'login.html')        

@login_required(login_url='/login/')
def mr_dashboard_view(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return render(request, 'dashboard.html', {'error': 'Employee profile missing'})

    today = timezone.now().date()
    
    day_start = DayStart.objects.filter(employee=employee, date=today).first()
    is_day_started = day_start is not None
    is_day_ended = DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists()
    
    daily_plan = DailyTourPlan.objects.filter(mtp__employee=employee, date=today, mtp__status='Approved').first()
    tp = daily_plan 

    if request.method == "POST" and "add_extra_route" in request.POST:
        new_route_id = request.POST.get('extra_route')
        if new_route_id and day_start and not is_day_ended:
            day_start.routes.add(new_route_id)
            messages.success(request, "Extra route successfully add ho gaya!")
        return redirect('mr_dashboard')
    
    active_routes = []
    available_routes = []
    pending_doctors = []
    visited_docs = []
    pending_chemists = []
    visited_chems = []
    
    if is_day_started:
        active_routes = day_start.routes.all()
        active_route_ids = active_routes.values_list('id', flat=True)
        
        my_all_route_ids = set(list(Doctor.objects.filter(allocated_to=employee).values_list('route_id', flat=True)) + list(Chemist.objects.filter(allocated_to=employee).values_list('route_id', flat=True)))
        available_routes = Route.objects.filter(id__in=my_all_route_ids).exclude(id__in=active_route_ids)

        # NAYA DCR LOGIC
        daily_dcr = DailyDCR.objects.filter(employee=employee, date=today).first()
        visited_doc_ids = set()
        visited_chem_ids = set()
        
        if daily_dcr:
            # Hum seedha Visit objects pass kar rahe hain jisse HTML me ID mil sake
            visited_docs = daily_dcr.visits.filter(doctor__isnull=False).select_related('doctor')
            visited_chems = daily_dcr.visits.filter(chemist__isnull=False).select_related('chemist')
            
            visited_doc_ids = set(visited_docs.values_list('doctor_id', flat=True))
            visited_chem_ids = set(visited_chems.values_list('chemist_id', flat=True))
        
        all_doctors = Doctor.objects.filter(allocated_to=employee, route__in=active_routes)
        pending_doctors = [d for d in all_doctors if d.id not in visited_doc_ids]
        
        all_chemists = Chemist.objects.filter(allocated_to=employee, route__in=active_routes)
        pending_chemists = [c for c in all_chemists if c.id not in visited_chem_ids]

    context = {
        'employee': employee,
        'today': today,
        'active_routes': active_routes,
        'available_routes': available_routes,
        'pending_doctors': pending_doctors,
        'visited_doctors': visited_docs,
        'pending_chemists': pending_chemists,
        'visited_chemists': visited_chems,
        'is_day_started': is_day_started, 
        'is_day_ended': is_day_ended,     
        'tp': tp
    }
    return render(request, 'dashboard.html', context)


@login_required(login_url='/login/')
def day_end_view(request):
    employee = request.user.employee
    today = timezone.now().date()
    
    if not DayStart.objects.filter(employee=employee, date=today).exists():
        messages.error(request, "Pehle Day Start karein, tabhi Day End hoga!")
        return redirect('mr_dashboard')

    day_closed = DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists()
    
    if request.method == "POST" and not day_closed:
        DayEnd.objects.get_or_create(employee=employee, date=today, defaults={'is_closed': True})
        return redirect('mr_dashboard')
        
    daily_dcr = DailyDCR.objects.filter(employee=employee, date=today).first()
    
    total_visits = 0
    total_samples = 0
    total_orders = 0
    pending_docs_count = 0

    if daily_dcr:
        visits = daily_dcr.visits.all()
        total_visits = visits.count()
        
        samples_orders = DCRProductDetail.objects.filter(visit__in=visits).aggregate(
            t_samples=Sum('sample_qty'), t_orders=Sum('order_qty')
        )
        total_samples = samples_orders['t_samples'] or 0
        total_orders = samples_orders['t_orders'] or 0

    daily_plan = DailyTourPlan.objects.filter(mtp__employee=employee, date=today, mtp__status='Approved').first()
    if daily_plan:
        all_docs = Doctor.objects.filter(allocated_to=employee, route=daily_plan.route).count()
        visited_docs = daily_dcr.visits.filter(doctor__isnull=False).count() if daily_dcr else 0
        pending_docs_count = max(0, all_docs - visited_docs)

    context = {
        'today': today,
        'day_closed': day_closed,
        'total_visits': total_visits,
        'total_samples': total_samples,
        'total_orders': total_orders,
        'pending_docs_count': pending_docs_count
    }
    return render(request, 'day_end.html', context)

@login_required(login_url='/login/')
def doctor_visit_view(request, doc_id):
    employee = request.user.employee
    today = timezone.now().date()
    
    if not DayStart.objects.filter(employee=employee, date=today).exists():
        messages.error(request, "Visit shuru karne se pehle Day Start karein!")
        return redirect('mr_dashboard')
        
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        messages.error(request, "Aaj ka din close ho chuka hai. Ab visit add nahi ho sakti!")
        return redirect('mr_dashboard')
        
    doctor = get_object_or_404(Doctor, id=doc_id)
    products = Product.objects.all()

    if request.method == "POST":
        remark_text = request.POST.get('remark', '')
        
        # NAYA DCR VISITS LOGIC
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=today)

        visit = DCRVisit.objects.create(
            daily_dcr=daily_dcr, 
            route=doctor.route, 
            doctor=doctor,
            remark=remark_text
        )

        for product in products:
            is_detailed = request.POST.get(f'detailed_{product.id}') == 'on' 
            sample_qty = int(request.POST.get(f'sample_{product.id}') or 0)
            order_qty = int(request.POST.get(f'order_{product.id}') or 0)

            if is_detailed or sample_qty > 0 or order_qty > 0:
                DCRProductDetail.objects.create(
                    visit=visit,
                    product=product,
                    is_detailed=is_detailed,
                    sample_qty=sample_qty,
                    order_qty=order_qty
                )
        
        return redirect('mr_dashboard')

    return render(request, 'visit_form.html', {'doctor': doctor, 'products': products})   

@login_required(login_url='/login/')
def chemist_visit_view(request, chem_id):
    chemist = get_object_or_404(Chemist, id=chem_id)
    employee = request.user.employee
    today = timezone.now().date()
    
    if not DayStart.objects.filter(employee=employee, date=today).exists():
        messages.error(request, "Visit shuru karne se pehle Day Start karein!")
        return redirect('mr_dashboard')
        
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        messages.error(request, "Aaj ka din close ho chuka hai!")
        return redirect('mr_dashboard')
        
    products = Product.objects.all()

    if request.method == "POST":
        # NAYA DCR VISITS LOGIC
        daily_dcr, _ = DailyDCR.objects.get_or_create(employee=employee, date=today)
        
        visit = DCRVisit.objects.create(
            daily_dcr=daily_dcr,
            route=chemist.route, 
            chemist=chemist
        )
        
        for product in products:
            order_qty = request.POST.get(f'order_{product.id}', 0)
            if order_qty and int(order_qty) > 0:
                DCRProductDetail.objects.create(
                    visit=visit,
                    product=product,
                    sample_qty=0,
                    order_qty=int(order_qty)
                )
        return redirect('mr_dashboard')
        
    context = {
        'chemist': chemist,
        'products': products,
        'today': today
    }
    return render(request, 'chemist_visit.html', context)


@login_required(login_url='/login/')
def manager_report_view(request):
    today = timezone.now().date()
    
    mr_reports = DailyDCR.objects.filter(date=today).annotate(
        total_visits=Count('visits'),
        total_samples=Sum('visits__product_details__sample_qty'),
        total_orders=Sum('visits__product_details__order_qty')
    ).values('employee__name', 'total_visits', 'total_samples', 'total_orders')
    
    grand_total_orders = DCRProductDetail.objects.filter(visit__daily_dcr__date=today).aggregate(total=Sum('order_qty'))['total'] or 0

    context = {
        'today': today,
        'mr_reports': mr_reports,
        'grand_total_orders': grand_total_orders
    }
    return render(request, 'manager_report.html', context)


@login_required(login_url='/login/')
def day_start_view(request):
    employee = request.user.employee
    today_str = str(timezone.now().date())
    today = timezone.now().date() 
    
    if DayStart.objects.filter(employee=employee, date=today).exists():
        messages.warning(request, "Aapka aaj ka Day pehle hi Start ho chuka hai!")
        return redirect('mr_dashboard')
        
    started_dates = DayStart.objects.filter(employee=employee).values_list('date', flat=True)
    ended_dates = DayEnd.objects.filter(employee=employee, is_closed=True).values_list('date', flat=True)
    pending_dates = sorted(list(set(started_dates) - set(ended_dates)))
    
    doc_terr = Doctor.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)
    chem_terr = Chemist.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)
    my_territory_ids = set(list(doc_terr) + list(chem_terr))
    territories = Territory.objects.filter(id__in=my_territory_ids)

    if request.method == "POST":
        selected_date = request.POST.get('date')
        territory_id = request.POST.get('territory')
        
        if selected_date and territory_id:
            territory = get_object_or_404(Territory, id=territory_id)
            day_start, created = DayStart.objects.get_or_create(
                employee=employee,
                date=selected_date,
                defaults={'territory': territory}
            )
            
            daily_plan = DailyTourPlan.objects.filter(mtp__employee=employee, date=selected_date, mtp__status='Approved').first()
            if daily_plan and created:
                day_start.routes.add(daily_plan.route)
                
            return redirect('mr_dashboard')

    context = {
        'today_str': today_str,
        'territories': territories,
        'pending_dates': pending_dates,
    }
    return render(request, 'day_start.html', context)

@login_required(login_url='/login/')
def request_hub_view(request):
    return render(request, 'request_hub.html')

@login_required(login_url='/login/')
def add_doctor_view(request):
    employee = request.user.employee
    
    my_terr_ids = set(list(Doctor.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)) + list(Chemist.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)))
    my_route_ids = set(list(Doctor.objects.filter(allocated_to=employee).values_list('route_id', flat=True)) + list(Chemist.objects.filter(allocated_to=employee).values_list('route_id', flat=True)))
    
    territories = Territory.objects.filter(id__in=my_terr_ids)
    routes = Route.objects.filter(id__in=my_route_ids)
    
    if request.method == "POST":
        name = request.POST.get('name')
        specialty = request.POST.get('specialty')
        territory_id = request.POST.get('territory')
        route_id = request.POST.get('route')
        
        if name and territory_id and route_id:
            Doctor.objects.create(name=name, specialty=specialty, territory_id=territory_id, route_id=route_id, allocated_to=employee)
            return redirect('request_hub')
            
    return render(request, 'add_doctor.html', {'territories': territories, 'routes': routes})

@login_required(login_url='/login/')
def add_chemist_view(request):
    employee = request.user.employee
    
    my_terr_ids = set(list(Doctor.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)) + list(Chemist.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)))
    my_route_ids = set(list(Doctor.objects.filter(allocated_to=employee).values_list('route_id', flat=True)) + list(Chemist.objects.filter(allocated_to=employee).values_list('route_id', flat=True)))
    
    territories = Territory.objects.filter(id__in=my_terr_ids)
    routes = Route.objects.filter(id__in=my_route_ids)
    
    if request.method == "POST":
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        territory_id = request.POST.get('territory')
        route_id = request.POST.get('route')
        
        if name and territory_id and route_id:
            Chemist.objects.create(name=name, phone=phone, territory_id=territory_id, route_id=route_id, allocated_to=employee)
            return redirect('request_hub')
            
    return render(request, 'add_chemist.html', {'territories': territories, 'routes': routes})

@login_required(login_url='/login/')
def add_tour_program_view(request):
    employee = request.user.employee
    
    doc_routes = Doctor.objects.filter(allocated_to=employee).values_list('route_id', flat=True)
    chem_routes = Chemist.objects.filter(allocated_to=employee).values_list('route_id', flat=True)
    my_route_ids = set(list(doc_routes) + list(chem_routes))
    routes = Route.objects.filter(id__in=my_route_ids)
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'create_mtp':
            month = int(request.POST.get('month'))
            year = int(request.POST.get('year'))
            
            if MonthlyTourProgram.objects.filter(employee=employee, month=month, year=year).exists():
                messages.error(request, f"{month}/{year} ka MTP pehle hi ban chuka hai!")
            else:
                MonthlyTourProgram.objects.create(employee=employee, month=month, year=year, status='Draft')
            return redirect('add_tour_program')
            
        elif action == 'add_daily_plan':
            mtp_id = request.POST.get('mtp_id')
            date_str = request.POST.get('date')
            route_id = request.POST.get('route')
            
            mtp = get_object_or_404(MonthlyTourProgram, id=mtp_id, employee=employee)
            
            if mtp.status != 'Draft':
                messages.error(request, "Sirf Draft MTP mein hi routes add kar sakte hain.")
                return redirect('add_tour_program')
                
            if DailyTourPlan.objects.filter(mtp=mtp, date=date_str).exists():
                messages.error(request, f"{date_str} ka plan pehle hi add ho chuka hai.")
            else:
                DailyTourPlan.objects.create(mtp=mtp, date=date_str, route_id=route_id)
            return redirect('add_tour_program')
            
        elif action == 'delete_daily_plan':
            plan_id = request.POST.get('plan_id')
            DailyTourPlan.objects.filter(id=plan_id, mtp__employee=employee, mtp__status='Draft').delete()
            return redirect('add_tour_program')
            
        elif action == 'submit_mtp':
            mtp_id = request.POST.get('mtp_id')
            MonthlyTourProgram.objects.filter(id=mtp_id, employee=employee, status='Draft').update(status='Pending')
            messages.success(request, "Tour Program approval ke liye manager ko bhej diya gaya hai!")
            return redirect('request_hub')

    draft_mtps = MonthlyTourProgram.objects.filter(employee=employee, status='Draft').prefetch_related('daily_plans')
            
    context = {
        'routes': routes,
        'draft_mtps': draft_mtps,
        'current_year': timezone.now().year
    }
    return render(request, 'add_tour_program.html', context)


@login_required(login_url='/login/')
def view_hub_view(request):
    employee = request.user.employee
    
    my_tps = MonthlyTourProgram.objects.filter(employee=employee).order_by('-year', '-month')
    my_doctors = Doctor.objects.filter(allocated_to=employee)
    my_chemists = Chemist.objects.filter(allocated_to=employee)
    
    my_dcrs = DailyDCR.objects.filter(employee=employee).order_by('-date')

    my_terr_ids = set(list(my_doctors.values_list('territory_id', flat=True)) + list(my_chemists.values_list('territory_id', flat=True)))
    my_territories = Territory.objects.filter(id__in=my_terr_ids)

    context = {
        'my_tps': my_tps,
        'my_doctors': my_doctors,
        'my_chemists': my_chemists,
        'my_territories': my_territories,
        'my_dcrs': my_dcrs 
    }
    return render(request, 'view_hub.html', context)

# ==========================================
# DELETE VISIT FUNCTION
# ==========================================
@login_required(login_url='/login/')
def delete_visit_view(request, visit_id):
    employee = request.user.employee
    today = timezone.now().date()
    
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        messages.error(request, "Day close ho chuka hai, ab visit delete nahi ho sakti!")
        return redirect('mr_dashboard')
        
    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee, daily_dcr__date=today)
    
    target = visit.doctor.name if visit.doctor else (visit.chemist.name if visit.chemist else "Unknown")
    visit.delete()
    
    messages.success(request, f"{target} ki visit successfully delete ho gayi.")
    return redirect('mr_dashboard')

# ==========================================
# VIEW DCR REPORT
# ==========================================
@login_required(login_url='/login/')
def view_dcr_report(request, dcr_id):
    employee = request.user.employee
    daily_dcr = get_object_or_404(DailyDCR.objects.prefetch_related('visits__product_details__product', 'visits__doctor', 'visits__chemist'), id=dcr_id, employee=employee)
    
    context = {
        'daily_dcr': daily_dcr,
        'visits': daily_dcr.visits.all()
    }
    return render(request, 'view_dcr_report.html', context)