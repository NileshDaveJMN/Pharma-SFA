"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.static import serve # 🌟 NAYA IMPORT

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('SFA.urls')),
    
    # 🌟 FIX: Explicitly serve media files even when DEBUG=False (For Render testing)
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]