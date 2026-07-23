from SFA.models import SystemNotification, DirectMessage

def notification_counts(request):
    if request.user.is_authenticated and hasattr(request.user, 'employee'):
        employee = request.user.employee
        return {
            'unread_notif_count': SystemNotification.objects.filter(
                employee=employee, is_read=False
            ).count(),
            'unread_msg_count': DirectMessage.objects.filter(
                receiver=employee, is_read=False
            ).count(),
        }
    return {
        'unread_notif_count': 0,
        'unread_msg_count': 0,
    }