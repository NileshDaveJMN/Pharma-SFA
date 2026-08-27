from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from SFA.models import Employee, InternalMessage, MessageAttachment

# 🚀 OPTIMIZATION: Project ka standard team fetcher import kiya taaki recursive N+1 loop na lage
from SFA.services.team import get_full_team_employees

def get_employee_from_user(request):
    try:
        return request.user.employee
    except AttributeError:
        return None

# 1. Inbox Fetch API
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inbox_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)

    # 🚀 OPTIMIZATION: Sender aur Attachments ko 1 hi query mein RAM mein load kar liya
    msgs = InternalMessage.objects.filter(receiver=employee)\
        .select_related('sender')\
        .prefetch_related('attachments')\
        .order_by('-sent_at')
        
    data = []
    for m in msgs:
        attachments = [{
            'id': att.id,
            'url': request.build_absolute_uri(att.file.url),
            'name': att.file.name.split('/')[-1]
        } for att in m.attachments.all()]
        
        data.append({
            'id': m.id,
            'sender_name': m.sender.name,
            'sender_id': m.sender.id,
            'subject': m.subject,
            'body': m.body,
            'is_read': m.is_read,
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
        
        receiver = Employee.objects.get(id=receiver_id, company=employee.company)
        
        msg = InternalMessage.objects.create(
            sender=employee,
            receiver=receiver,
            subject=subject,
            body=body,
            parent_message_id=parent_id if parent_id else None
        )
        
        files = request.FILES.getlist('attachments')
        # 🚀 OPTIMIZATION: bulk_create use karke DB calls ko bachaya
        if files:
            MessageAttachment.objects.bulk_create([
                MessageAttachment(message=msg, file=f) for f in files
            ])
            
        return Response({'status': 'success', 'message_id': msg.id})
        
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)


# 5. Employees List API (Updated with Hierarchy Logic)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def employee_list_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)
        
    managers = employee.get_my_managers(include_inactive=False)
    admins = list(Employee.objects.filter(company=employee.company, designation='Admin', is_active=True))
    
    # 🚀 OPTIMIZATION: Recursion DB queries ko standard team fetcher se replace kiya
    subordinates = list(get_full_team_employees(employee).exclude(id=employee.id)) if employee.designation != 'MR' else []
    
    all_emps = managers + subordinates + admins
    unique_emps = {e.id: e for e in all_emps if e.id != employee.id}
    
    data = [{'id': e.id, 'name': e.name, 'designation': e.designation} for e in unique_emps.values()]
    return Response({'employees': data})

# 6. Sent Items API
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sent_items_view(request):
    employee = get_employee_from_user(request)
    if not employee:
        return Response({'error': 'Employee not found'}, status=404)

    # 🚀 OPTIMIZATION: Sender, Receiver aur Attachments ko 1 hi query mein pack kiya
    msgs = InternalMessage.objects.filter(sender=employee)\
        .select_related('sender', 'receiver')\
        .prefetch_related('attachments')\
        .order_by('-sent_at')
        
    data = []
    for m in msgs:
        attachments = [{
            'id': att.id,
            'url': request.build_absolute_uri(att.file.url),
            'name': att.file.name.split('/')[-1]
        } for att in m.attachments.all()]
        
        data.append({
            'id': m.id,
            'sender_name': m.sender.name,
            'receiver_name': m.receiver.name, 
            'sender_id': m.sender.id,
            'subject': m.subject,
            'body': m.body,
            'is_read': m.is_read,
            'sent_at': timezone.localtime(m.sent_at).strftime('%d %b, %H:%M'),
            'attachments': attachments
        })
    return Response({'messages': data})    
