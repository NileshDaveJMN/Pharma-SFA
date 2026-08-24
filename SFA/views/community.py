from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment, Territory

# ==============================================================================
# 📢 1. COMMUNITY FEED (WebApp Wall)
# ==============================================================================
@login_required
def community_feed(request):
    emp = request.user.employee
    events = FieldEvent.objects.filter(is_shared_in_community=True).order_by('-created_at')
    
    # Template mein like status check karne ke liye flag add kar rahe hain
    for ev in events:
        ev.is_liked_by_me = ev.likes.filter(employee=emp).exists()
        
    return render(request, 'community_feed.html', {'events': events})

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
        
        # Checkbox handling for boolean
        is_shared = request.POST.get('is_shared_in_community') == 'on'
        
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
        
        # 🌟 Multiple Photos Upload Handling
        photos = request.FILES.getlist('photos')
        for photo in photos:
            EventPhoto.objects.create(event=event, photo=photo)
            
        messages.success(request, "Event successfully created!")
        return redirect('community_feed')
        
    return render(request, 'create_event.html')

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
