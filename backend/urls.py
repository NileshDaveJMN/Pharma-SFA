"""
URL configuration for backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('SFA.urls')),
]

# 🌟 FIX: Ab ye DEBUG=False (Render) par bhi media files serve karega
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)