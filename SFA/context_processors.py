from SFA.models import SystemNotification, InternalMessage

def notification_counts(request):
    if request.user.is_authenticated and hasattr(request.user, 'employee'):
        employee = request.user.employee
        return {
            'unread_notif_count': SystemNotification.objects.filter(
                employee=employee, is_read=False
            ).count(),
            # 🌟 FIX: pehle DirectMessage (purana, ab dead system) count hota
            # tha — isliye badge kabhi update hi nahi hota tha. Ab InternalMessage
            # (email system) count hota hai, Flutter ke api/messaging.py ke
            # unread_message_count_view jaisa hi.
            'unread_msg_count': InternalMessage.objects.filter(
                receiver=employee, is_read=False
            ).count(),
        }
    return {
        'unread_notif_count': 0,
        'unread_msg_count': 0,
    }