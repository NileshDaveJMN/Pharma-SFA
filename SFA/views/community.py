from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Territory
from django.core.paginator import Paginator
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Territory, Doctor, Chemist, Employee
from django.db.models import Count
from SFA.models import Employee # Agar Employee import nahi hai toh kar lijiye

# ==============================================================================
# 📢 1. COMMUNITY FEED (WebApp Wall)
# ==============================================================================
@login_required
def community_feed(request):
    emp = request.user.employee
    # Saari events nikalenge
    event_list = FieldEvent.objects.filter(is_shared_in_community=True).select_related('employee', 'territory', 'doctor', 'chemist').order_by('-created_at')
    
    # 🌟 PAGINATION LOGIC: Ek baar mein sirf 15 events
    paginator = Paginator(event_list, 15) 
    page_number = request.GET.get('page')
    events = paginator.get_page(page_number)
    
    for ev in events:
        ev.is_liked_by_me = ev.likes.filter(employee=emp).exists()
        
    # Leaderboard (Top 5)
    leaderboard = Employee.objects.annotate(
        total_events=Count('field_events')
    ).filter(total_events__gt=0).order_by('-total_events')[:5]
        
    return render(request, 'community_feed.html', {
        'events': events, 
        'leaderboard': leaderboard
    })

# ==============================================================================
# 📸 2. CREATE EVENT (WebApp form submission)
# ==============================================================================
@login_required
def create_event(request):
    emp = request.user.employee
    
    if request.method == 'POST':
        subject = request.POST.get('subject')
        category = request.POST.get('category', 'Other')
        description = request.POST.get('description', '')
        is_shared = request.POST.get('is_shared_in_community') == 'on'
        
        doc_id = request.POST.get('doctor')
        chem_id = request.POST.get('chemist')
        
        if not subject:
            messages.error(request, "Event Subject is required!")
            return redirect('create_event')
            
        event = FieldEvent.objects.create(
            employee=emp,
            subject=subject,
            category=category,
            description=description,
            is_shared_in_community=is_shared
        )
        
        # Save Doctor / Chemist if selected
        if doc_id: event.doctor_id = doc_id
        if chem_id: event.chemist_id = chem_id
        event.save()
        
        photos = request.FILES.getlist('photos')
        for photo in photos:
            EventPhoto.objects.create(event=event, photo=photo)
            
        messages.success(request, "Event successfully created!")
        return redirect('event_report') # Create hone ke baad seedha Report par bhejo taaki wahan se share kar sake
        
    # GET request - Show form with doctors/chemists
    doctors = Doctor.objects.filter(company=emp.company)# Aap chahein toh filter laga sakte hain (e.g., company wise)
    chemists = Chemist.objects.filter(company=emp.company)
    
    return render(request, 'create_event.html', {'doctors': doctors, 'chemists': chemists})

# ==============================================================================
# 👍 3. TOGGLE LIKE (WebApp)
# ==============================================================================
@login_required
def toggle_like(request, event_id):
    emp = request.user.employee
    event = get_object_or_404(FieldEvent, id=event_id)
    
    like, created = EventLike.objects.get_or_create(event=event, employee=emp)
    if not created:
        like.delete() # Pehle se tha toh Unlike kar do
        
    # Agar future mein AJAX (bina page reload) like banana ho, toh JsonResponse use hoga
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': created, 'likes_count': event.likes.count()})
        
    # Default: Jis page se like kiya tha wahi wapas bhej do
    return redirect(request.META.get('HTTP_REFERER', 'community_feed'))

# ==============================================================================
# 💬 4. ADD COMMENT (WebApp)
# ==============================================================================
@login_required
def add_comment(request, event_id):
    emp = request.user.employee
    event = get_object_or_404(FieldEvent, id=event_id)
    
    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        if comment_text:
            EventComment.objects.create(event=event, employee=emp, comment=comment_text)
            messages.success(request, "Comment added successfully!")
            
    return redirect(request.META.get('HTTP_REFERER', 'community_feed'))

@login_required
def share_event_from_report(request, event_id):
    # Sirf wahi MR share kar payega jisne event banaya hai
    event = get_object_or_404(FieldEvent, id=event_id, employee=request.user.employee)
    
    event.is_shared_in_community = True
    event.save()
    
    messages.success(request, "Event shared to Community Wall successfully! 🎉")
    return redirect('event_report')
from SFA.services.team import get_full_team_employees
import calendar
from django.utils import timezone

MONTHS_CHOICES = [(i, calendar.month_name[i]) for i in range(1, 13)]

# ==============================================================================
# 📸 5. EVENT REPORT (Reports Hub)
# ==============================================================================
@login_required
def event_report(request):
    emp = request.user.employee
    # Manager hai toh uski poori team (khud + subordinates), MR hai toh sirf khud
    team_emps = get_full_team_employees(emp)
    is_manager_view = team_emps.count() > 1

    # 🌟 Month/Year filter — DEFAULT current month.
    # Ye zaroori hai: bina filter ke saara history load hoga, aur 1-2 saal
    # baad events/photos badhne par ye page bahut heavy ho jayega / server
    # crash kara sakta hai. Month-wise filter se hamesha ek bounded query rahegi.
    today = timezone.now().date()
    try:
        selected_month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        selected_month = today.month
    try:
        selected_year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        selected_year = today.year

    if is_manager_view:
        # Manager ko pehle apna MR select karna hoga — tabhi query chalegi.
        raw_emp_id = request.GET.get('employee_id')
        selected_emp_id = int(raw_emp_id) if raw_emp_id else None
        if selected_emp_id:
            events = FieldEvent.objects.filter(
                employee_id=selected_emp_id,
                event_date__year=selected_year,
                event_date__month=selected_month,
            )
        else:
            events = FieldEvent.objects.none()
    else:
        # MR khud — apna hi data, employee select karne ki zarurat nahi.
        selected_emp_id = emp.id
        events = FieldEvent.objects.filter(
            employee_id=emp.id,
            event_date__year=selected_year,
            event_date__month=selected_month,
        )

    events = events.select_related('employee', 'territory', 'doctor', 'chemist') \
                    .prefetch_related('photos') \
                    .order_by('-event_date', '-created_at')

    return render(request, 'event_report.html', {
        'events': events,
        'is_manager_view': is_manager_view,
        'team_employees': team_emps,
        'selected_emp_id': selected_emp_id,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months_choices': MONTHS_CHOICES,
    })

# ==============================================================================
# 🚀 6. SHARE EVENT FROM REPORT
# ==============================================================================
@login_required
def share_event_from_report(request, event_id):
    # Sirf wahi MR share kar payega jisne event banaya hai
    event = get_object_or_404(FieldEvent, id=event_id, employee=request.user.employee)
    
    event.is_shared_in_community = True
    event.save()
    
    messages.success(request, "Event shared to Community Wall successfully! 🎉")
    return redirect('event_report')
