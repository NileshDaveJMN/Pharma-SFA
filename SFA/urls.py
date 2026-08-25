# SFA/urls.py
from django.urls import path, include
from django.shortcuts import redirect
from rest_framework.authtoken.views import obtain_auth_token

from . import views
from SFA.views import auth as auth_views

# Miscellaneous / Requests
from SFA.views.requests import weekly_secondary_sale_view, weekly_sale_history_view, manage_focus_products
from SFA.views import community as community_views
from SFA.views.mr_sales import mr_primary_sale_entry

# Masters
from .views.masters import edit_chemist_list_view, edit_chemist_view, view_doctor_profile, view_chemist_profile, bulk_network_upload_view, promo_dispatch_view, gift_campaign_view
from .views import superadmin

# ==============================================================
# 🚀 THE NEW MODULAR IMPORTS (Speed Optimized Architecture)
# ==============================================================

# 1. Daily Operations & HR
from SFA.views.reports_ops import (
    dcr_report_view, expense_report_view, network_report_view, 
    route_report_view, tour_plan_report_view, holiday_list_view, 
    route_playback_view, view_dcr_report
)

# 2. Primary & Secondary Business (Sales)
from SFA.views.reports_sales import (
    smart_secondary_report_view, primary_sales_report_view, 
    party_wise_sale_entry_view, classify_rx_entry_view, 
    party_rx_report_view, dr_wise_sale_report_view, 
    product_sales_report_view, product_master_view
)

# 3. Promotions & Free Claims
from SFA.views.reports_promo import (
    free_claim_view, free_claim_view_readonly, approve_free_claims_view, 
    mr_inventory_view, gift_distribution_report, doctor_roi_report
)

# 4. Analytics & Targets
from SFA.views.reports_analytics import (
    analysis_hub_view, sales_summary_report_view, target_setting_view, 
    review_target_view, dr_visit_history_view
)

# 5. Manager Approvals
from SFA.views.reports_approvals import (
    manager_approval_hub, manager_report_view, review_mtp_view, 
    approve_activity_view
)


urlpatterns = [
    # 🌟 FIX: Root domain par login page redirect karna
    path('', lambda request: redirect('login/')),
    
    # Admin tools / Onboarding URL
    path('admin-tools/onboard-company/', superadmin.onboard_company_view, name='onboard_company'),
    path('admin-tools/transfer-data/', views.transfer_data_view, name='transfer_data'),

    # APIs (Mobile App)
    path('api/login/', obtain_auth_token, name='api_login'),
    
    # Web Dashboard & Workflow
    path('login/', views.login_view, name='login'), 
    path('logout/', auth_views.logout_view, name='logout'),
    
    path('dashboard/', views.mr_dashboard_view, name='mr_dashboard'), 
    path('start/', views.day_start_view, name='day_start'),
    path('day-end/', views.day_end_view, name='day_end'),
    path('profile/', views.profile_view, name='profile'),
    
    # Customer Visits & Profiles
    path('visit/doctor/<int:doc_id>/', views.doctor_visit_view, name='doctor_visit'),
    path('visit/chemist/<int:chem_id>/', views.chemist_visit_view, name='chemist_visit'),
    path('visit/edit/<int:visit_id>/', views.edit_visit_view, name='edit_visit'),    
    path('visit/delete/<int:visit_id>/', views.delete_visit_view, name='delete_visit'),
    path('doctor/profile/<int:doc_id>/', view_doctor_profile, name='view_doctor_profile'),
    path('chemist/profile/<int:chem_id>/', view_chemist_profile, name='view_chemist_profile'),
    path('update-location/<str:role>/<int:target_id>/', views.update_location_view, name='update_location'),
    
    # Hubs & Management Requests
    path('request/', views.request_hub_view, name='request_hub'),
    path('request/add-doctor/', views.add_doctor_view, name='add_doctor'),
    path('request/add-chemist/', views.add_chemist_view, name='add_chemist'),
    path('request/add-tp/', views.add_tour_program_view, name='add_tour_program'),
    path('request/add-route/', views.add_route_view, name='add_route'),
    path('request/holiday/', views.request_holiday_view, name='request_holiday'),
    path('request/leave/', views.apply_leave_view, name='apply_leave'),
    path('my-requests/', views.my_requests_view, name='my_requests'),
    
    # 🌟 NEW FEATURE: Focus Products Manage URL
    path('request/focus-products/', manage_focus_products, name='manage_focus_products'),
    
    # Views & Calendars
    path('view/', views.view_hub_view, name='view_hub'),
    path('view/products/', product_master_view, name='product_master'),
    path('view/holidays/', holiday_list_view, name='holiday_list'),
    path('view/dr-visit-history/', dr_visit_history_view, name='dr_visit_history'),
    path('calendar/', views.calendar_view, name='calendar_view'),
    
    # Reports & Approvals
    path('report/', manager_report_view, name='manager_report'),
    path('approvals/', manager_approval_hub, name='manager_approvals'),
    path('approvals/mtp/<int:mtp_id>/', review_mtp_view, name='review_mtp'),
    path('approvals/expense/<int:exp_id>/', views.review_expense_view, name='review_expense'),
    path('activity/approve/<int:activity_id>/', approve_activity_view, name='approve_activity'),
    
    # Miscellaneous Reports
    path('reports/primary-sales/', primary_sales_report_view, name='primary_sales_report'),
    path('reports/smart-secondary-statement/', smart_secondary_report_view, name='smart_secondary_statement'),
    path('reports/products/', product_sales_report_view, name='product_report'),
    path('reports/dcr/', dcr_report_view, name='dcr_report'),
    path('dcr/view/<int:dcr_id>/', view_dcr_report, name='view_dcr_report'),
    path('reports/tour-plan/', tour_plan_report_view, name='tour_plan_report'),
    path('reports/network/', network_report_view, name='network_report'),
    path('reports/routes/', route_report_view, name='route_report'),
    path('reports/expenses/', expense_report_view, name='expense_report'),
    path('reports/free-claim/', free_claim_view, name='free_claim_report'),
    path('reports/approve-free-claims/', approve_free_claims_view, name='approve_free_claims'),
    path('reports/analysis-hub/', analysis_hub_view, name='analysis_hub'),
    path('reports/sales-summary/', sales_summary_report_view, name='sales_summary_report'),
    path('report/route-playback/<int:employee_id>/<str:date_str>/', route_playback_view, name='route_playback'),
    
    # Hub Views
    path('hub/view/gift-report/', gift_distribution_report, name='gift_distribution_report'),
    path('hub/view/doctor-roi/', doctor_roi_report, name='doctor_roi_report'),
    path('hub/gift-campaign/', gift_campaign_view, name='gift_campaign'),
    
    # Data Uploads
    path('view/upload-primary-sales/', views.upload_primary_sales_view, name='upload_primary_sales'),
    path('network/bulk-upload/', bulk_network_upload_view, name='bulk_network_upload'),
    
    # Expenses & Settings
    path('expense/', views.expense_hub_view, name='expense_hub'),
    path('target-setting/', target_setting_view, name='target_setting'),
    path('review-target/<int:target_id>/', review_target_view, name='review_target'),
    
    # 🎯 Party Wise Sales & Rx Flow
    path('api/get-chemists/<int:doctor_id>/', views.get_chemists_for_doctor, name='get_chemists_for_doctor'),
    path('api/get-products/<int:doctor_id>/<int:chemist_id>/', views.get_products_for_dr_chemist, name='get_products_for_dr_chemist'),
    path('reports/party-wise-sale/', party_wise_sale_entry_view, name='party_wise_sale_entry'),
    path('reports/classify-rx/', classify_rx_entry_view, name='classify_rx_entry'),
    path('reports/party-rx-report/', party_rx_report_view, name='party_rx_report'),
    path('reports/dr-wise-sale-view/', dr_wise_sale_report_view, name='dr_wise_sale_report'),

    # ✏️ EDIT HUB & EDIT RECORDS
    path('edit-hub/', views.edit_hub_view, name='edit_hub'),
    path('edit/doctor/list/', views.edit_doctor_list_view, name='edit_doctor_list'),
    path('edit/doctor/<int:doc_id>/', views.edit_doctor_view, name='edit_doctor'),
    path('edit-chemist-list/', edit_chemist_list_view, name='edit_chemist_list'),
    path('edit-chemist/<int:chem_id>/', edit_chemist_view, name='edit_chemist'),
    
    # 💬 Communications & Alerts Hub (Web)
    path('hub/notices/', views.notice_board_view, name='notice_board'),
    path('hub/notifications/', views.notification_list_view, name='notification_list'),
    path('hub/messages/', views.web_inbox_view, name='web_inbox'),
    path('hub/messages/compose/', views.web_compose_view, name='web_compose'),
    path('hub/messages/<int:msg_id>/', views.web_message_detail_view, name='web_message_detail'),
    
    # Other App flows
    path('promo-dispatch/', promo_dispatch_view, name='promo_dispatch'),
    path('my-inventory/', mr_inventory_view, name='mr_inventory'),
    path('resign-employee/', views.resign_employee_view, name='resign_employee'),
    path('organogram/', views.organogram_view, name='organogram'),
    path('promote-employee/', views.promote_employee_view, name='promote_employee'),
    path('free-claim-view/', free_claim_view_readonly, name='free_claim_view_readonly'),
    path('leave-status/', views.leave_status_view, name='leave_status'),
    path('reports/weekly-secondary-sale/', weekly_secondary_sale_view, name='weekly_secondary_sale'),
    path('reports/weekly-sale-history/', weekly_sale_history_view, name='weekly_sale_history'),
    
    # ── Community & Events (WebApp) ───────────────────────────────────────────
    path('community/', community_views.community_feed, name='community_feed'),
    path('community/create/', community_views.create_event, name='create_event'),
    path('community/like/<int:event_id>/', community_views.toggle_like, name='toggle_like'),
    path('community/comment/<int:event_id>/', community_views.add_comment, name='add_comment'),    
    path('reports/events/<int:event_id>/share/', community_views.share_event_from_report, name='share_event_from_report'),
    path('reports/events/', community_views.event_report, name='event_report'),
    
    # MR Primary Sale Cart Entry
    path('mr-primary-sale/', mr_primary_sale_entry, name='mr_primary_sale_entry'),

]
