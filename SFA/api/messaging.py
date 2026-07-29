from django.utils import timezone  # 🌟 NAYA IMPORT
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from SFA.models import Employee, InternalMessage, MessageAttachment

# 検 Helper function: Token se Employee nikalne ke liye
def get_employee_from_user(request):
    try:
        # Agar aapke Employee model mein 'user' field hai (OneToOne)
        return Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Agar Employee khud User model hai, toh request.user return karein
        return request.user 
    except Exception:
        return None

# 1. Inbox Fetch API
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inbox_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)

    msgs = InternalMessage.objects.filter(receiver=employee).order_by('-sent_at')
    data = []
    for m in msgs:
        attachments = []
        for att in m.attachments.all():
            attachments.append({
                'id': att.id,
                'url': request.build_absolute_uri(att.file.url),
                'name': att.file.name.split('/')[-1]
            })
        data.append({
            'id': m.id,
            'sender_name': m.sender.name,
            'sender_id': m.sender.id,
            'subject': m.subject,
            'body': m.body,
            'is_read': m.is_read,
            # 🌟 FIX: Convert to localtime and format as "30 Jul, 00:29"
            'sent_at': timezone.localtime(m.sent_at).strftime('%d %b, %H:%M'),
            'attachments': attachments
        })
    return Response({'messages': data})

# 2. Unread Count API
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_message_count_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)
    count = InternalMessage.objects.filter(receiver=employee, is_read=False).count()
    return Response({'unread_count': count})

# 3. Mark as Read API
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_message_read_view(request, msg_id):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)
    try:
        msg = InternalMessage.objects.get(id=msg_id, receiver=employee)
        msg.is_read = True
        msg.save()
        return Response({'status': 'success'})
    except InternalMessage.DoesNotExist:
        return Response({'status': 'error', 'message': 'Not found'}, status=404)

# 4. Send / Forward / Reply Email API
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_message_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)
        
    try:
        receiver_id = request.data.get('receiver_id')
        subject = request.data.get('subject')
        body = request.data.get('body')
        parent_id = request.data.get('parent_id')
        
        # 検 FIX: Sirf usi company ke employee ko mail bhej sake
        receiver = Employee.objects.get(id=receiver_id, company=employee.company)
        
        msg = InternalMessage.objects.create(
            sender=employee,
            receiver=receiver,
            subject=subject,
            body=body,
            parent_message_id=parent_id if parent_id else None
        )
        
        # Attachments Save karna
        files = request.FILES.getlist('attachments')
        for f in files:
            MessageAttachment.objects.create(message=msg, file=f)
            
        return Response({'status': 'success', 'message_id': msg.id})
        
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)

# 検 NAYA FUNCTION: Niche ki poori team chain nikalne ke liye
def get_all_subordinates(employee):
    subs = []
    # Sirf active subordinates ko fetch karein
    direct_subs = Employee.objects.filter(manager=employee, is_active=True)
    for sub in direct_subs:
        subs.append(sub)
        subs.extend(get_all_subordinates(sub)) # Recursion for their subordinates
    return subs

# 5. Employees List API (Updated with Hierarchy Logic)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def employee_list_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)
        
    # 1. Apne upar wale saare managers (is_active=True)
    managers = employee.get_my_managers(include_inactive=False)
    
    # 2. Company ke Admins ko hamesha include karein (taaki MR admin ko mail kar sake)
    admins = list(Employee.objects.filter(company=employee.company, designation='Admin', is_active=True))
    
    # 3. Agar user manager hai, toh niche ki poori team nikalein
    subordinates = get_all_subordinates(employee) if employee.designation != 'MR' else []
    
    # Sabko combine karein aur Duplicate (Khud ko) hata dein
    all_emps = managers + subordinates + admins
    unique_emps = {e.id: e for e in all_emps if e.id != employee.id}
    
    # 検 FIX: designation field alag se bhejni hai taaki Flutter usko filter kar sake
    data = [{'id': e.id, 'name': e.name, 'designation': e.designation} for e in unique_emps.values()]
    return Response({'employees': data})

# 6. Sent Items API (Jo messages user ne khud bheje hain)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sent_items_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)

    # Sender = current employee wale messages
    msgs = InternalMessage.objects.filter(sender=employee).order_by('-sent_at')
    data = []
    for m in msgs:
        attachments = []
        for att in m.attachments.all():
            attachments.append({
                'id': att.id,
                'url': request.build_absolute_uri(att.file.url),
                'name': att.file.name.split('/')[-1]
            })
        data.append({
            'id': m.id,
            'sender_name': m.sender.name,
            'receiver_name': m.receiver.name, # 検 Naya field receiver ka naam
            'sender_id': m.sender.id,
            'subject': m.subject,
            'body': m.body,
            'is_read': m.is_read,
            # 🌟 FIX: Convert to localtime and format as "30 Jul, 00:29"
            'sent_at': timezone.localtime(m.sent_at).strftime('%d %b, %H:%M'),
            'attachments': attachments
        })
    return Response({'messages': data})    
