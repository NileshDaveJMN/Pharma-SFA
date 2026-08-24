from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from SFA.models import FieldEvent, EventPhoto, EventLike, EventComment

# ==============================================================================
# 📢 1. GET COMMUNITY FEED (Sari posts dekhne ke liye)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_community_feed(request):
    emp = request.user.employee
    # Sirf wahi events laao jo community mein shared hain, sabse naye upar
    events = FieldEvent.objects.filter(is_shared_in_community=True).order_by('-created_at')
    
    data = []
    for ev in events:
        # Event ki saari photos nikalna
        photos = [p.photo.url for p in ev.photos.all() if p.photo]
        
        # Likes ka data
        likes_count = ev.likes.count()
        is_liked_by_me = ev.likes.filter(employee=emp).exists()
        
        # Comments ka data
        comments = [{
            'employee_name': c.employee.name,
            'comment': c.comment,
            'time': c.created_at.strftime('%d %b %Y %I:%M %p')
        } for c in ev.comments.all().order_by('-created_at')]
        
        data.append({
            'id': ev.id,
            'subject': ev.subject,
            'description': ev.description or "",
            'category': ev.category,
            'creator_name': ev.employee.name,
            'territory': ev.territory.name if ev.territory else "N/A",
            'time': ev.created_at.strftime('%d %b %Y %I:%M %p'),
            'photos': photos,
            'likes_count': likes_count,
            'is_liked_by_me': is_liked_by_me,
            'comments': comments
        })
        
    return Response(data)

# ==============================================================================
# 📸 2. CREATE NEW EVENT (MR field se event aur photos banayega)
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_create_event(request):
    emp = request.user.employee
    subject = request.data.get('subject')
    category = request.data.get('category', 'Other')
    description = request.data.get('description', '')
    
    # Flutter se string 'true' aayega ya boolean, dono handle kar lenge
    is_shared = str(request.data.get('is_shared_in_community', 'false')).lower() == 'true'
    
    if not subject:
        return Response({'error': 'Event Subject zaroori hai'}, status=400)
        
    # Naya Event Save Karein
    event = FieldEvent.objects.create(
        employee=emp,
        subject=subject,
        category=category,
        description=description,
        is_shared_in_community=is_shared
    )
    
    # Optional fields (Doctor / Chemist / Territory)
    if request.data.get('doctor_id'):
        event.doctor_id = request.data.get('doctor_id')
    if request.data.get('chemist_id'):
        event.chemist_id = request.data.get('chemist_id')
    if request.data.get('territory_id'):
        event.territory_id = request.data.get('territory_id')
    event.save()
    
    # 🌟 Multiple Photos Handling (Flutter list bheje dega 'photos' key mein)
    photos = request.FILES.getlist('photos')
    for photo in photos:
        EventPhoto.objects.create(event=event, photo=photo)
        
    return Response({'message': 'Event successfully created!', 'event_id': event.id})

# ==============================================================================
# 👍 3. LIKE / UNLIKE POST
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_like(request):
    emp = request.user.employee
    event_id = request.data.get('event_id')
    event = get_object_or_404(FieldEvent, id=event_id)
    
    # Check karega agar like exist karta hai
    like, created = EventLike.objects.get_or_create(event=event, employee=emp)
    
    if not created:
        like.delete() # Agar pehle se liked tha, toh delete kar do (Unlike)
        return Response({'message': 'Unliked', 'liked': False})
        
    return Response({'message': 'Liked', 'liked': True})

# ==============================================================================
# 💬 4. ADD COMMENT
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_add_comment(request):
    emp = request.user.employee
    event_id = request.data.get('event_id')
    comment_text = request.data.get('comment')
    
    if not comment_text:
        return Response({'error': 'Comment khali nahi ho sakta'}, status=400)
        
    event = get_object_or_404(FieldEvent, id=event_id)
    EventComment.objects.create(event=event, employee=emp, comment=comment_text)
    
    return Response({'message': 'Comment successfully added!'})
