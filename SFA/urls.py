# SFA/urls.py
from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token
from . import views
from django.shortcuts import redirect
urlpatterns = [
    # APIs (Mobile App ke liye)
    path('api/doctors/', views.doctor_list_api, name='doctor-list'),
    path('api/login/', obtain_auth_token, name='api_login'),
    
    # Web Dashboard (MVP Frontend ke liye)
    path('login/', views.login_view, name='user_login'), 
    path('dashboard/', views.mr_dashboard_view, name='mr_dashboard'), 
    path('day-end/', views.day_end_view, name='day_end'),
    path('visit/doctor/<int:doc_id>/', views.doctor_visit_view, name='doctor_visit'),
        path('report/', views.manager_report_view, name='manager_report'),
        path('start/', views.day_start_view, name='day_start'),
        path('request/', views.request_hub_view, name='request_hub'),
path('request/add-doctor/', views.add_doctor_view, name='add_doctor'),
path('request/add-chemist/', views.add_chemist_view, name='add_chemist'),
path('request/add-tp/', views.add_tour_program_view, name='add_tour_program'),
path('view/', views.view_hub_view, name='view_hub'),
    path('visit/chemist/<int:chem_id>/', views.chemist_visit_view, name='chemist_visit'),
    path('emergency-clean-data/', views.clean_database_view, name='clean_data'),
path('', lambda request: redirect('login/')),
]
