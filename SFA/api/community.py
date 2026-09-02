from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Employee, Doctor, Chemist, Territory
from SFA.services.team import get_full_team_employees
from .reports_helpers import _resolve_selected_employee, _employee_brief
from django.db.models import Prefetch
from django.core.cache import cache
from SFA.models import FieldEvent, EventPhoto, EventComment, EventLike, Employee, Doctor, Chemist, Territory

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_community_feed(request):
    emp = request.user.employee

    # 🚀 N+1 FIXED: photos, comments (+employee), likes — sab ek query mein prefetch
    comments_qs = EventComment.objects.select_related('employee').order_by('-created_at')
    event_list = FieldEvent.objects.filter(
        is_shared_in_community=True
    ).select_related(
        'employee', 'territory', 'doctor', 'chemist'
    ).prefetch_related(
        'photos',
        Prefetch('comments', queryset=comments_qs),
        'likes',
    ).order_by('-created_at')

    paginator = Paginator(event_list, 10)
    events = paginator.get_page(request.GET.get('page', 1))

    feed_data = []
    for ev in events:
        # 🚀 Sab kuch PREFETCHED data se — loop mein ZERO queries
        photos_list = [
    p.photo.url.replace('/upload/', '/upload/c_limit,w_800,q_auto,f_auto/')
    for p in ev.photos.all()
]

        comments_list = [{
            'employee_name': c.employee.name,
            'comment': c.comment,
            'time': c.created_at.strftime('%d %b %Y %I:%M %p')
        } for c in ev.comments.all()]   # Prefetch queryset order-by laga raha hai

        likes = list(ev.likes.all())
        likes_count = len(likes)                                # count() → Python len
        is_liked_by_me = any(l.employee_id == emp.id for l in likes)  # exists() → Python

        feed_data.append({
            'id': ev.id,
            'subject': ev.subject,
            'description': ev.description or "",
            'category': ev.category,
            'creator_name': ev.employee.name,
            'territory': ev.territory.name if ev.territory else "N/A",
            'time': ev.created_at.strftime('%d %b %Y %I:%M %p'),
            'photos': photos_list,
            'likes_count': likes_count,
            'is_liked_by_me': is_liked_by_me,
            'comments': comments_list
        })

    # 🚀 LEADERBOARD: Cache (5 min TTL) + 🐛 company filter fix
    today = timezone.now().date()
    cache_key = f"lb_{emp.company_id}_{today.year}_{today.month}"
    leaderboard_data = cache.get(cache_key)
    if leaderboard_data is None:
        leaderboard_qs = Employee.objects.filter(company=emp.company).annotate(   # 🐛 SaaS leak fix
            total_events=Count('field_events', filter=Q(
                field_events__created_at__year=today.year,
                field_events__created_at__month=today.month,
            ))
        ).filter(total_events__gt=0).order_by('-total_events')[:5]
        leaderboard_data = [{'name': e.name, 'events_count': e.total_events} for e in leaderboard_qs]
        cache.set(cache_key, leaderboard_data, 300)   # 5 minute

    return Response({
        'feed': feed_data,
        'leaderboard': leaderboard_data,
        'has_next_page': events.has_next(),
        'current_page': events.number,
        'total_pages': paginator.num_pages
    })

# ==============================================================================
# 📸 2. GET EVENT REPORT (Exact Match with Expense/Stockist Report Logic)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_event_report(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    # 🌟 EXPENSE REPORT JESA LOGIC: Automatically team & selected employee resolve karega
    selected_emp, team_employees = _resolve_selected_employee(request, employee)

    today = timezone.now().date()
    try:
        selected_month = int(request.GET.get('month', today.month))
    except (TypeError, ValueError):
        selected_month = today.month
    try:
        selected_year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        selected_year = today.year

    # Ab selected_emp ke hisaab se data aayega (Manager ne dropdown se choose kiya hoga)
    events = FieldEvent.objects.filter(
        employee_id=selected_emp.id,
        event_date__year=selected_year,
        event_date__month=selected_month,
    ).select_related('employee', 'territory', 'doctor', 'chemist') \
     .prefetch_related('photos') \
     .order_by('-event_date', '-created_at')
    
    report_data = []
    for ev in events:
        photos_list = [
    p.photo.url.replace('/upload/', '/upload/c_limit,w_800,q_auto,f_auto/')
    for p in ev.photos.all()
]

        report_data.append({
            'id': ev.id,
            'subject': ev.subject,
            'category': ev.category,
            'creator_name': ev.employee.name,
            'date': ev.event_date.strftime('%d %b %Y'),
            'is_shared': ev.is_shared_in_community,
            'description': ev.description or "",
            'photos': photos_list,
            # Sirf khud ka event share kar sakta hai
            'can_share': not ev.is_shared_in_community and ev.employee == employee 
        })
        
    # 🌟 EXPENSE REPORT JESA RESPONSE STRUCTURE
    return Response({
        'selected_employee': _employee_brief(selected_emp),
        'team_employees': [_employee_brief(e) for e in team_employees] if employee.designation != 'MR' else [],
        'events': report_data
    })
# ==============================================================================
# 🚀 3. SHARE PRIVATE EVENT TO COMMUNITY
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_share_event(request):
    emp = request.user.employee
    event_id = request.data.get('event_id')
    event = get_object_or_404(FieldEvent, id=event_id, employee=emp)
    event.is_shared_in_community = True
    event.save()
    return Response({'message': 'Event successfully shared to Community Wall!'})

# ==============================================================================
# 📝 4. CREATE NEW EVENT (Webapp Logic Matched)
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
    
    # Webapp: doc_id & chem_id save
    doc_id = request.data.get('doctor_id')
    if doc_id and str(doc_id).isdigit(): 
        event.doctor_id = int(doc_id)
        
    chem_id = request.data.get('chemist_id')
    if chem_id and str(chem_id).isdigit(): 
        event.chemist_id = int(chem_id)
        
    event.save()
    
    # Webapp: request.FILES.getlist('photos')
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