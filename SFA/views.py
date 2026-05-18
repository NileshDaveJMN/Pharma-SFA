# SFA/views.py
from django.contrib import messages
from .models import DayStart, Territory 
from django.utils import timezone
from django.db.models import Sum, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Doctor, Chemist, TourProgram, DayEnd, Product, Route, DCR, DCRProductDetail
from .serializers import DoctorSerializer
@api_view(['GET'])
@permission_classes([IsAuthenticated]) # 🔒 Sirf login kiya hua banda hi dekh sakega
def doctor_list_api(request):
    # 1. Jo user login hai (Token ke zariye), uska Employee record dhoondho
    user = request.user
    
    try:
        # request.user.employee wahi hai jo aapne admin mein attach kiya hai
        employee = user.employee 
        
        # 2. Sirf wahi doctors filter karo jo IS employee ko allocated hain
        doctors = Doctor.objects.filter(allocated_to=employee)
        
        # 3. JSON mein badal kar bhej do
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
# Yeh tag ensure karega ki bina login koi dashboard na dekh sake
@login_required(login_url='/login/')
def mr_dashboard_view(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return render(request, 'dashboard.html', {'error': 'Employee profile missing'})

    today = timezone.now().date()
    
    # 🔒 STRICT COMPLIANCE FLAGS
    # Check karein kya aaj Day Start hua hai
    is_day_started = DayStart.objects.filter(employee=employee, date=today).exists()
    # Check karein kya aaj ka Day End (lock) ho chuka hai
    is_day_ended = DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists()

    tp = TourProgram.objects.filter(employee=employee, date=today, status='Approved').first()
    
    route = None
    pending_doctors = []
    visited_doctors = []
    pending_chemists = []
    visited_chemists = []
    
    if tp:
        route = tp.route
        # 1. Aaj is MR ne jin Doctors/Chemists ko visit kar liya unki IDs nikalo
        visited_doc_ids = set(DCR.objects.filter(employee=employee, date=today, doctor__isnull=False).values_list('doctor_id', flat=True))
        visited_chem_ids = set(DCR.objects.filter(employee=employee, date=today, chemist__isnull=False).values_list('chemist_id', flat=True))
        
        # 2. Saare Doctors/Chemists ko do alag lists mein baant do (Pending aur Visited)
        all_doctors = Doctor.objects.filter(allocated_to=employee, route=route)
        pending_doctors = [d for d in all_doctors if d.id not in visited_doc_ids]
        visited_doctors = [d for d in all_doctors if d.id in visited_doc_ids]
        
        all_chemists = Chemist.objects.filter(allocated_to=employee, route=route)
        pending_chemists = [c for c in all_chemists if c.id not in visited_chem_ids]
        visited_chemists = [c for c in all_chemists if c.id in visited_chem_ids]

    context = {
        'employee': employee,
        'today': today,
        'route': route,
        'pending_doctors': pending_doctors,
        'visited_doctors': visited_doctors,
        'pending_chemists': pending_chemists,
        'visited_chemists': visited_chemists,
        'is_day_started': is_day_started, # <-- Naya flag pass kiya
        'is_day_ended': is_day_ended,     # <-- Naya flag pass kiya
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

    # LOCK 2: Agar pehle hi Day End ho chuka hai, toh dobara na ho
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        messages.warning(request, "Aaj ka kaam pehle hi freeze ho chuka hai!")
        return redirect('mr_dashboard')

    # 1. Check karein ki kya aaj ka din pehle hi lock ho chuka hai
    day_closed = DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists()
    
    # 2. Agar button dabaya (POST request), toh lock kar do
    if request.method == "POST" and not day_closed:
        DayEnd.objects.get_or_create(employee=employee, date=today, defaults={'is_closed': True})
        return redirect('mr_dashboard')
        
    # 3. Poore din ka Summary nikalein
    dcrs = DCR.objects.filter(employee=employee, date=today)
    total_visits = dcrs.count()
    
    # Product details se sum nikalein
    samples_orders = DCRProductDetail.objects.filter(dcr__employee=employee, dcr__date=today).aggregate(
        t_samples=Sum('sample_qty'), t_orders=Sum('order_qty')
    )
    total_samples = samples_orders['t_samples'] or 0
    total_orders = samples_orders['t_orders'] or 0
    
    # 4. Check karein ki koi Doctor chhut toh nahi gaya (Pending Visits)
    tp = TourProgram.objects.filter(employee=employee, date=today, status='Approved').first()
    pending_docs_count = 0
    if tp:
        all_docs = Doctor.objects.filter(allocated_to=employee, route=tp.route).count()
        visited_docs = dcrs.filter(doctor__isnull=False).count()
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
        
    # LOCK 2: Day end ho chuka hai toh bhaga do
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        messages.error(request, "Aaj ka din close ho chuka hai. Ab visit add nahi ho sakti!")
        return redirect('mr_dashboard')
    doctor = get_object_or_404(Doctor, id=doc_id)
    products = Product.objects.all()

    # Agar galti se Day End ke baad koi yahan aa jaye, toh wapas bhej do
    if DayEnd.objects.filter(employee=employee, date=today, is_closed=True).exists():
        return redirect('mr_dashboard')

    if request.method == "POST":
        remark_text = request.POST.get('remark', '')
        # 1. Pehle aaj ki visit ka main record (DCR) banayein
        dcr, created = DCR.objects.get_or_create(
            employee=employee, 
            date=today, 
            route=doctor.route, 
            doctor=doctor,
            remark=remark_text
        )

        # 2. Har product ka form data check karein
        for product in products:
            # Checkbox se 'on' mila ya nahi
            is_detailed = request.POST.get(f'detailed_{product.id}') == 'on' 
            # Sample aur Order ki quantity nikalein (kuch nahi dala toh 0)
            sample_qty = int(request.POST.get(f'sample_{product.id}') or 0)
            order_qty = int(request.POST.get(f'order_{product.id}') or 0)

            # Agar MR ne is dawai par kuch bhi action liya hai, toh hi save karein
            if is_detailed or sample_qty > 0 or order_qty > 0:
                DCRProductDetail.objects.create(
                    dcr=dcr,
                    product=product,
                    is_detailed=is_detailed,
                    sample_qty=sample_qty,
                    order_qty=order_qty
                )
        
        # Save hone ke baad wapas Dashboard par bhej dein
        return redirect('mr_dashboard')

    return render(request, 'visit_form.html', {'doctor': doctor, 'products': products})   

@login_required(login_url='/login/')
def manager_report_view(request):
    today = timezone.now().date()
    
    # 🔥 MR-Wise Grouping Logic: Ek MR ne total kitne calls kiye, kitna sample diya aur kitna order laya
    mr_reports = DCR.objects.filter(date=today).values(
        'employee__name', 'route__name'
    ).annotate(
        total_visits=Count('id'),
        total_samples=Sum('product_details__sample_qty'),
        total_orders=Sum('product_details__order_qty')
    )
    
    grand_total_orders = DCRProductDetail.objects.filter(dcr__date=today).aggregate(total=Sum('order_qty'))['total'] or 0

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
    
    # 🔥 SMART FILTER: Sirf MR ki apni Territories
    doc_terr = Doctor.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)
    chem_terr = Chemist.objects.filter(allocated_to=employee).values_list('territory_id', flat=True)
    my_territory_ids = set(list(doc_terr) + list(chem_terr))
    territories = Territory.objects.filter(id__in=my_territory_ids)

    if request.method == "POST":
        selected_date = request.POST.get('date')
        territory_id = request.POST.get('territory')
        
        if selected_date and territory_id:
            territory = get_object_or_404(Territory, id=territory_id)
            DayStart.objects.get_or_create(
                employee=employee,
                date=selected_date,
                defaults={'territory': territory}
            )
            return redirect('mr_dashboard')

    context = {
        'today_str': today_str,
        'territories': territories,
        'pending_dates': pending_dates,
    }
    return render(request, 'day_start.html', context)

# SFA/views.py ke sabse niche paste karein

@login_required(login_url='/login/')
def request_hub_view(request):
    return render(request, 'request_hub.html')

# 🧑‍⚕️ NAYA DOCTOR ADD KARNE KE LIYE
@login_required(login_url='/login/')
def add_doctor_view(request):
    employee = request.user.employee
    
    # 🔥 SMART FILTER
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
    
    # 🔥 SMART FILTER
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

# 📅 TOUR PROGRAM (MTP) SUBMIT KARNE KE LIYE
@login_required(login_url='/login/')
def add_tour_program_view(request):
    employee = request.user.employee
    
    # 🔥 SMART FILTER: Sirf MR ke apne Routes
    doc_routes = Doctor.objects.filter(allocated_to=employee).values_list('route_id', flat=True)
    chem_routes = Chemist.objects.filter(allocated_to=employee).values_list('route_id', flat=True)
    my_route_ids = set(list(doc_routes) + list(chem_routes))
    routes = Route.objects.filter(id__in=my_route_ids)
    
    if request.method == "POST":
        action = request.POST.get('action')
        
        if action == 'add_draft':
            date = request.POST.get('date')
            route_id = request.POST.get('route')
            existing_tp = TourProgram.objects.filter(employee=employee, date=date).first()
            if existing_tp and existing_tp.status in ['Pending', 'Approved']:
                messages.error(request, f"{date} ka Tour Program pehle hi '{existing_tp.status}' hai. Aap isme badlaav nahi kar sakte!")
                return redirect('add_tour_program')
            if date and route_id:
                TourProgram.objects.update_or_create(
                    employee=employee,
                    date=date,
                    defaults={'route_id': route_id, 'status': 'Draft'}
                )
            return redirect('add_tour_program')
            
        elif action == 'delete_draft':
            tp_id = request.POST.get('tp_id')
            TourProgram.objects.filter(id=tp_id, employee=employee, status='Draft').delete()
            return redirect('add_tour_program')
            
        elif action == 'submit_final':
            TourProgram.objects.filter(employee=employee, status='Draft').update(status='Pending')
            return redirect('request_hub')

    draft_mtps = TourProgram.objects.filter(employee=employee, status='Draft').order_by('date')
            
    context = {
        'routes': routes,
        'draft_mtps': draft_mtps
    }
    return render(request, 'add_tour_program.html', context)

# SFA/views.py ke sabse niche add karein

@login_required(login_url='/login/')
def view_hub_view(request):
    employee = request.user.employee
    
    my_tps = TourProgram.objects.filter(employee=employee).order_by('-date')
    my_doctors = Doctor.objects.filter(allocated_to=employee)
    my_chemists = Chemist.objects.filter(allocated_to=employee)
    
    # 🔥 SMART FILTER for View Tab
    my_terr_ids = set(list(my_doctors.values_list('territory_id', flat=True)) + list(my_chemists.values_list('territory_id', flat=True)))
    my_territories = Territory.objects.filter(id__in=my_terr_ids)

    context = {
        'my_tps': my_tps,
        'my_doctors': my_doctors,
        'my_chemists': my_chemists,
        'my_territories': my_territories,
    }
    return render(request, 'view_hub.html', context)
@login_required(login_url='/login/')
def chemist_visit_view(request, chem_id):
    chemist = get_object_or_404(Chemist, id=chem_id)
    employee = request.user.employee
    today = timezone.now().date()
    
    # Check karein ki aaj ka TP approved hai ya nahi
    tp = TourProgram.objects.filter(employee=employee, date=today, status='Approved').first()
    if not tp:
        return redirect('mr_dashboard')
        
    products = Product.objects.all()

    
    if request.method == "POST":
        # 1. Chemist ke liye ek DCR entry banayein
        dcr = DCR.objects.create(
            employee=employee,
            date=today,
            route=tp.route,
            chemist=chemist
        )
        
        # 2. Jo bhi order quantity aayi hai, use save karein
        for product in products:
            order_qty = request.POST.get(f'order_{product.id}', 0)
            
            # Chemist visit mein hum sample 0 aur detailed False rakh rahe hain
            if order_qty and int(order_qty) > 0:
                DCRProductDetail.objects.create(
                    dcr=dcr,
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
