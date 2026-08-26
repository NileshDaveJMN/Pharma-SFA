from django.core.cache import cache
from SFA.models import SystemNotification, InternalMessage

def notification_counts(request):
    if request.user.is_authenticated and hasattr(request.user, 'employee'):
        employee = request.user.employee
        
        # 🚀 CACHING MAGIC: 60 seconds tak count memory mein save rakho
        cache_key = f'nav_counts_{employee.id}'
        counts = cache.get(cache_key)
        
        if counts is None:
            counts = {
                'unread_notif_count': SystemNotification.objects.filter(employee=employee, is_read=False).count(),
                'unread_msg_count': InternalMessage.objects.filter(receiver=employee, is_read=False).count(),
            }
            cache.set(cache_key, counts, 60) # 60 seconds cache timeout
            
        return counts
        
    return {
        'unread_notif_count': 0,
        'unread_msg_count': 0,
    }
