from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Territory
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Territory, Doctor, Chemist, Employee
from django.db.models import Count
from SFA.models import Employee # Agar Employee import nahi hai toh kar lijiye

# ==============================================================================
# 📢 1. COMMUNITY FEED (WebApp Wall)
# ==============================================================================
@login_required
def community_feed(request):
    emp = request.user.employee
    events = FieldEvent.objects.filter(is_shared_in_community=True).order_by('-created_at')
    
    for ev in events:
        ev.is_liked_by_me = ev.likes.filter(employee=emp).exists()
        
    # ==========================================
    # 🏆 LEADERBOARD LOGIC (Top 5 Performers)
    # ==========================================
    # Un employees ko nikal rahe hain jinhone sabse zyada 'shared' events kiye hain
    leaderboard = Employee.objects.annotate(
        total_events=Count('field_events')
    ).filter(total_events__gt=0).order_by('-total_events')[:5] # Top 5
        
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
