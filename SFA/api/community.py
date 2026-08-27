from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Employee, Doctor, Chemist, Territory
from SFA.services.team import get_full_team_employees

# ==============================================================================
# 📢 1. GET COMMUNITY FEED & LEADERBOARD (Flutter)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_community_feed(request):
    emp = request.user.employee
    event_list = FieldEvent.objects.filter(is_shared_in_community=True).order_by('-created_at')
    
    # 🌟 PAGINATION FOR FLUTTER: 15 events per API call
    paginator = Paginator(event_list, 15)
    page_number = request.GET.get('page', 1) # Default page 1
    events = paginator.get_page(page_number)
    
    feed_data = []
    for ev in events:
        feed_data.append({
            'id': ev.id,
            'subject': ev.subject,
            'description': ev.description or "",
            'category': ev.category,
            'creator_name': ev.employee.name,
            'territory': ev.territory.name if ev.territory else "N/A",
            'time': ev.created_at.strftime('%d %b %Y %I:%M %p'),
            'photos': [p.photo.url for p in ev.photos.all() if p.photo],
            'likes_count': ev.likes.count(),
            'is_liked_by_me': ev.likes.filter(employee=emp).exists(),
            'comments': [{
                'employee_name': c.employee.name,
                'comment': c.comment,
                'time': c.created_at.strftime('%d %b %Y %I:%M %p')
            } for c in ev.comments.all().order_by('-created_at')]
        })
        
    # 🌟 LEADERBOARD LOGIC (CURRENT MONTH ONLY)
    today = timezone.now().date()
    leaderboard_qs = Employee.objects.annotate(
        total_events=Count(
            'field_events',
            filter=Q(
                field_events__created_at__year=today.year,
                field_events__created_at__month=today.month,
            )
        )
    ).filter(total_events__gt=0).order_by('-total_events')[:5]
    
    leaderboard_data = [{'name': e.name, 'events_count': e.total_events} for e in leaderboard_qs]
        
    return Response({
        'feed': feed_data,
        'leaderboard': leaderboard_data,
        # Flutter developer ko batane ke liye ki aur events baaki hain ya nahi
        'has_next_page': events.has_next(), 
        'current_page': events.number,
        'total_pages': paginator.num_pages
    })

# ==============================================================================
# 📸 2. GET EVENT REPORT (Private + Public for Team) - 🌟 OPTIMIZED
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_event_report(request):
    emp = request.user.employee
    team_emps = get_full_team_employees(emp)
    is_manager_view = team_emps.count() > 1

    # 🌟 Month/Year filter — DEFAULT current month (Webapp jaisa)
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
        # 🌟 Manager ko pehle apna MR select karna hoga — tabhi query chalegi.
        raw_emp_id = request.GET.get('employee_id')
        selected_emp_id = int(raw_emp_id) if raw_emp_id else None
        
        if selected_emp_id:
            events = FieldEvent.objects.filter(
                employee_id=selected_emp_id,
                event_date__year=selected_year,
                event_date__month=selected_month,
            )
        else:
            events = FieldEvent.objects.none() # Jab tak MR select na kare, khaali list bhejo
    else:
        # MR khud — apna hi data, employee select karne ki zarurat nahi.
        selected_emp_id = emp.id
        events = FieldEvent.objects.filter(
            employee_id=emp.id,
            event_date__year=selected_year,
            event_date__month=selected_month,
        )

    # 🌟 Database query optimize karni hai (Webapp me thi, API me miss ho gayi thi)
    events = events.select_related('employee', 'territory', 'doctor', 'chemist') \
                    .prefetch_related('photos') \
                    .order_by('-event_date', '-created_at')
    
    report_data = []
    for ev in events:
        report_data.append({
            'id': ev.id,
            'subject': ev.subject,
            'category': ev.category,
            'creator_name': ev.employee.name,
            'date': ev.event_date.strftime('%d %b %Y'),
            'is_shared': ev.is_shared_in_community,
            'description': ev.description or "",
            'photos_count': ev.photos.count(),
            'can_share': not ev.is_shared_in_community and ev.employee == emp
        })
        
    return Response(report_data)
# ==============================================================================
# 🚀 3. SHARE PRIVATE EVENT TO COMMUNITY
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_share_event(request):
    emp = request.user.employee
    event_id = request.data.get('event_id')
    
    # Sirf wahi share kar payega jisne banaya hai
    event = get_object_or_404(FieldEvent, id=event_id, employee=emp)
    event.is_shared_in_community = True
    event.save()
    
    return Response({'message': 'Event successfully shared to Community Wall!'})

# ==============================================================================
# 📝 4. CREATE NEW EVENT (MR field se event aur photos banayega)
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_event(request):
    emp = request.user.employee
    subject = request.data.get('subject')
    category = request.data.get('category', 'Other')
    description = request.data.get('description', '')
    is_shared = str(request.data.get('is_shared_in_community', 'false')).lower() == 'true'
    
    if not subject:
        return Response({'error': 'Event Subject is required'}, status=400)
        
    event = FieldEvent.objects.create(
        employee=emp, subject=subject, category=category,
        description=description, is_shared_in_community=is_shared
    )
    
    # Safely parse IDs (Agar Flutter galti se empty string ya 'null' bhej de)
    doc_id = request.data.get('doctor_id')
    if doc_id and str(doc_id).isdigit(): 
        event.doctor_id = int(doc_id)
        
    chem_id = request.data.get('chemist_id')
    if chem_id and str(chem_id).isdigit(): 
        event.chemist_id = int(chem_id)
        
    terr_id = request.data.get('territory_id')
    if terr_id and str(terr_id).isdigit(): 
        event.territory_id = int(terr_id)
        
    event.save()
    
    photos = request.FILES.getlist('photos')
    for photo in photos:
        EventPhoto.objects.create(event=event, photo=photo)
        
    return Response({'message': 'Event successfully created!', 'event_id': event.id})

# ==============================================================================
# 👍 5. LIKE & 💬 6. COMMENT APIs
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_like(request):
    emp = request.user.employee
    event = get_object_or_404(FieldEvent, id=request.data.get('event_id'))
    like, created = EventLike.objects.get_or_create(event=event, employee=emp)
    if not created: like.delete()
    return Response({'message': 'Liked' if created else 'Unliked', 'liked': created})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_comment(request):
    emp = request.user.employee
    comment_text = request.data.get('comment')
    if not comment_text: return Response({'error': 'Comment required'}, status=400)
    event = get_object_or_404(FieldEvent, id=request.data.get('event_id'))
    EventComment.objects.create(event=event, employee=emp, comment=comment_text)
    return Response({'message': 'Comment added!'})
