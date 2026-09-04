from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
import calendar
from django.core.paginator import Paginator
from SFA.models import (
    FieldEvent, EventPhoto, EventLike, EventComment,
    Territory, Doctor, Chemist, Employee
)
from SFA.services.team import get_full_team_employees
from django.db.models import Count, Q

MONTHS_CHOICES = [(i, calendar.month_name[i]) for i in range(1, 13)]

# ==============================================================================
# 📢 1. COMMUNITY FEED (WebApp Wall)
# ==============================================================================
@login_required
def community_feed(request):
    emp = request.user.employee

    # 🌟 Company-scoped: sirf APNI company ke employees ki shared events
    event_list = FieldEvent.objects.filter(
        is_shared_in_community=True,
        employee__company=emp.company
    ).select_related('employee', 'territory', 'doctor', 'chemist').order_by('-created_at')

    # 🌟 PAGINATION LOGIC: Ek baar mein sirf 10 events
    paginator = Paginator(event_list, 10)
    page_number = request.GET.get('page')
    events = paginator.get_page(page_number)

    # 🚀 N+1 FIXED: mere likes EK query mein, phir Python set lookup
    my_liked_event_ids = set(EventLike.objects.filter(
        employee=emp, event__in=events
    ).values_list('event_id', flat=True))
    for ev in events:
        ev.is_liked_by_me = ev.id in my_liked_event_ids

    # 🌟 Leaderboard (Top 5) — monthly + 🛡️ company-scoped
    today = timezone.now().date()
    leaderboard = Employee.objects.filter(company=emp.company).annotate(
        total_events=Count(
            'field_events',
            filter=Q(
                field_events__created_at__year=today.year,
                field_events__created_at__month=today.month,
                field_events__employee__company=emp.company,
            )
        )
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

        # 🛡️ FIX: Company-scoped doctor/chemist — dusri company ka ID inject nahi hoga
        if doc_id:
            doc = Doctor.objects.filter(id=doc_id, company=emp.company).first()
            if doc:
                event.doctor = doc
        if chem_id:
            chem = Chemist.objects.filter(id=chem_id, company=emp.company).first()
            if chem:
                event.chemist = chem
        event.save()

        photos = request.FILES.getlist('photos')
        for photo in photos:
            EventPhoto.objects.create(event=event, photo=photo)

        messages.success(request, "Event successfully created!")
        return redirect('event_report')

    # GET request - Show form with doctors/chemists
    doctors = Doctor.objects.filter(company=emp.company)
    chemists = Chemist.objects.filter(company=emp.company)

    return render(request, 'create_event.html', {'doctors': doctors, 'chemists': chemists})

# ==============================================================================
# 👍 3. TOGGLE LIKE (WebApp)
# ==============================================================================
@login_required
def toggle_like(request, event_id):
    emp = request.user.employee
    # 🛡️ FIX: company-scope — dusri company ke event pe like nahi
    event = get_object_or_404(FieldEvent, id=event_id, employee__company=emp.company)

    like, created = EventLike.objects.get_or_create(event=event, employee=emp)
    if not created:
        like.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'liked': created, 'likes_count': event.likes.count()})

    return redirect(request.META.get('HTTP_REFERER', 'community_feed'))

# ==============================================================================
# 💬 4. ADD COMMENT (WebApp)
# ==============================================================================
@login_required
def add_comment(request, event_id):
    emp = request.user.employee
    # 🛡️ FIX: company-scope — dusri company ke event pe comment nahi
    event = get_object_or_404(FieldEvent, id=event_id, employee__company=emp.company)

    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        if comment_text:
            EventComment.objects.create(event=event, employee=emp, comment=comment_text)
            messages.success(request, "Comment added successfully!")

    return redirect(request.META.get('HTTP_REFERER', 'community_feed'))

# ==============================================================================
# 🚀 5. SHARE EVENT FROM REPORT (duplicate wala — ab sirf EK definition)
# ==============================================================================
@login_required
def share_event_from_report(request, event_id):
    # Sirf wahi MR share kar payega jisne event banaya hai
    event = get_object_or_404(FieldEvent, id=event_id, employee=request.user.employee)

    event.is_shared_in_community = True
    event.save()

    messages.success(request, "Event shared to Community Wall successfully! 🎉")
    return redirect('event_report')

# ==============================================================================
# 📸 6. EVENT REPORT (Reports Hub)
# ==============================================================================
@login_required
def event_report(request):
    emp = request.user.employee
    team_emps = get_full_team_employees(emp)
    is_manager_view = team_emps.count() > 1

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
        raw_emp_id = request.GET.get('employee_id')
        selected_emp_id = int(raw_emp_id) if raw_emp_id else None

        # 🛡️ IDOR FIX: Manager sirf APNI team ke member ki events dekh sakta hai
        if selected_emp_id and not team_emps.filter(id=selected_emp_id).exists():
            selected_emp_id = None

        if selected_emp_id:
            events = FieldEvent.objects.filter(
                employee_id=selected_emp_id,
                event_date__year=selected_year,
                event_date__month=selected_month,
            )
        else:
            events = FieldEvent.objects.none()
    else:
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