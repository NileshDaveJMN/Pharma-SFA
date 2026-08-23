"""
SFA/api/urls.py — Flutter REST API complete URL patterns
"""
from django.urls import path

# ── Core & App Modules ────────────────────────────────────────────────────────
from SFA.api import auth as auth_api
from SFA.api import core as core_api
from SFA.api import masters as masters_api
from SFA.api import sales as sales_api
from SFA.api import expenses as expenses_api
from SFA.api import reports as reports_api
from SFA.api import messaging # 🌟 Naya Messaging Import

# ── Specific Endpoint Imports ─────────────────────────────────────────────────
from SFA.api.masters import api_add_route
from SFA.api.pob_reports import api_pob_report
from SFA.api.reports_gift_distribution import api_gift_distribution_report
from SFA.api.reports_free_claim import api_free_claim_readonly
from SFA.api.reports_core import (
    api_primary_sales_report, 
    api_sales_summary_report,
    api_dr_wise_sale_report,
    api_party_rx_report,
    api_doctor_roi_report,
    api_analysis_hub, 
    api_doctor_visit_history, 
    api_route_report, 
    api_product_master, 
    api_mr_inventory, 
    api_receive_dispatch
)
from .secondary_sales import get_pending_stockists, get_focus_products, submit_weekly_sales, get_weekly_sale_detail, weekly_sale_history, api_rsm_manage_focus_products

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('auth/login/',    auth_api.api_login,     name='api_login'),
    path('auth/logout/',   auth_api.api_logout,    name='api_logout'),
    path('auth/profile/',  auth_api.api_profile,   name='api_profile'),
    path('auth/team/',     auth_api.api_team_tree, name='api_team_tree'),
    path('auth/organogram/', auth_api.api_organogram, name='api_organogram'),   
    path('auth/save-token/', auth_api.api_save_token, name='api_save_token'),

    # ── Core / DCR ────────────────────────────────────────────────────────────
    path('dashboard/',        core_api.api_dashboard,        name='api_dashboard'),
    path('day-start/',        core_api.api_day_start,        name='api_day_start'),
    path('day-end/',          core_api.api_day_end,          name='api_day_end'),
    path('notices/',          core_api.api_notices,          name='api_notices'),
    path('update-location/',  core_api.api_update_location,  name='api_update_location'),
    path('notifications/',    core_api.api_notifications,    name='api_notifications'),
    path('notifications/unread/', core_api.api_unread_notifications_count, name='api_unread_notifs_count'),    
    path('messages/',         core_api.api_messages,         name='api_messages'),
    path('my-requests/',      core_api.api_my_requests,      name='api_my_requests'),
    path('visits/<int:visit_id>/edit/', core_api.api_edit_visit, name='api_edit_visit'),
    path('mtp/',              core_api.api_mtp,              name='api_mtp'),
    path('calendar/events/',  core_api.api_calendar_events,  name='api_calendar_events'),    

    # ── Masters ───────────────────────────────────────────────────────────────
    path('doctors/',                       masters_api.api_doctors,             name='api_doctors'),
    path('doctors/<int:doc_id>/',          masters_api.api_doctor_detail,       name='api_doctor_detail'),
    path('doctors/<int:doc_id>/edit/',     masters_api.api_doctor_edit_request, name='api_doctor_edit'),
    
    path('chemists/',                      masters_api.api_chemists,            name='api_chemists'),
    path('chemists/<int:chem_id>/',        masters_api.api_chemist_detail,      name='api_chemist_detail'),
    path('chemists/<int:chem_id>/edit/',   masters_api.api_chemist_edit_request,name='api_chemist_edit'),
    
    path('routes/',                        masters_api.api_routes,              name='api_routes'),
    path('routes/add/',                    api_add_route,                       name='api_add_route'),
    
    path('territories/',                   masters_api.api_territories,         name='api_territories'),
    path('dropdowns/',                     masters_api.api_dropdowns,           name='api_dropdowns'),
    path('leaves/',                        masters_api.api_leaves,              name='api_leaves'),
    path('holidays/',                      masters_api.api_holidays,            name='api_holidays'),
    
    path('mappings/doctor/<int:doc_id>/chemists/', masters_api.api_doctor_chemists, name='api_doctor_chemists'),
    path('mappings/doctor/<int:doc_id>/chemist/<int:chem_id>/products/', masters_api.api_dr_chemist_products, name='api_dr_chemist_products'),

    # ── Sales, Targets & Claims ───────────────────────────────────────────────
    path('visits/today/',                    sales_api.api_today_visits,         name='api_today_visits'),
    path('visits/doctor/form/<int:doc_id>/', sales_api.api_doctor_visit_form,    name='api_doctor_visit_form'),
    path('visits/doctor/',                   sales_api.api_doctor_visit_submit,  name='api_doctor_visit_submit'),
    path('visits/chemist/',                  sales_api.api_chemist_visit_submit, name='api_chemist_visit_submit'),
    path('visits/<int:visit_id>/',           sales_api.api_delete_visit,         name='api_delete_visit'), 
    
    path('sales/party-wise/',                sales_api.api_party_wise_get,       name='api_party_wise_get'),
    path('sales/party-wise/submit/',         sales_api.api_party_wise_submit,    name='api_party_wise_submit'),    
    path('sales/targets/',                   sales_api.api_target_setting,       name='api_target_setting'),
    path('gift-campaign/',                   sales_api.api_gift_campaign,        name='api_gift_campaign'),

    # ── Expenses ──────────────────────────────────────────────────────────────
    path('expenses/',                          expenses_api.api_expense_list,   name='api_expense_list'),
    path('expenses/<int:report_id>/',          expenses_api.api_expense_detail, name='api_expense_detail'),
    path('expenses/<int:report_id>/save/',     expenses_api.api_expense_save,   name='api_expense_save'),
    path('expenses/<int:report_id>/submit/',   expenses_api.api_expense_submit, name='api_expense_submit'),
    path('expenses/<int:report_id>/reopen/',   expenses_api.api_expense_reopen, name='api_expense_reopen'),

    # ── Reports ──────────────────────────────────────────────────────────────
    path('reports/product-sales/',       reports_api.api_product_sales_report,   name='api_product_sales_report'),
    path('reports/dcr/',                 reports_api.api_dcr_report,             name='api_dcr_report'),
    path('reports/dcr/<int:dcr_id>/',    reports_api.api_dcr_detail,             name='api_dcr_detail'),
    path('reports/approvals/',           reports_api.api_approval_hub,           name='api_approval_hub'),
    path('reports/approvals/action/',    reports_api.api_approval_action,        name='api_approval_action'),
    path('reports/network/',             reports_api.api_network_report,         name='api_network_report'),
    path('reports/route-playback/<int:employee_id>/<str:date_str>/', reports_api.api_route_playback, name='api_route_playback'),
    path('reports/products/',            api_product_master,                     name='api_product_master'),
    path('reports/inventory/',           api_mr_inventory,                       name='api_inventory'),
    path('reports/inventory/receive/',   api_receive_dispatch,                   name='api_receive_dispatch'),
    path('reports/free-claims/',         reports_api.api_free_claims,            name='api_free_claims'),
    path('reports/tour-plan/',           reports_api.api_tour_plan_report,       name='api_tour_plan_report'),
    path('reports/expense/',             reports_api.api_expense_report,         name='api_expense_report'),
    path('reports/holidays/',            reports_api.api_holiday_list,           name='api_holiday_list'),
    path('reports/sales-summary/',       api_sales_summary_report,               name='api_sales_summary_report'),
    path('reports/primary-sales/',       api_primary_sales_report,               name='api_primary_sales_report'),
    path('reports/stockist-statement/',  reports_api.api_stockist_statement,     name='api_stockist_statement'),
    path('reports/pob/',                 api_pob_report,                         name='api_pob_report'),
    path('reports/dr-wise-sale/',        api_dr_wise_sale_report,                name='api_dr_wise_sale_report'),
    path('reports/party-rx/',            api_party_rx_report,                    name='api_party_rx_report'),
    path('reports/doctor-roi/',          api_doctor_roi_report,                  name='api_doctor_roi_report'),
    path('reports/analysis-hub/',        api_analysis_hub,                       name='api_analysis_hub'),
    path('reports/gift-distribution/',   api_gift_distribution_report,           name='api_gift_distribution_report'),
    path('reports/doctor-visits/',       api_doctor_visit_history,               name='api_doctor_visit_history'),
    path('reports/free-claim-readonly/', api_free_claim_readonly,                name='api_free_claim_readonly'),
    path('reports/route-report/',        api_route_report,                       name='api_route_report'),

    # ── 🌟 Internal Messaging System (Email) ──────────────────────────────────
    path('messaging/inbox/',             messaging.inbox_view,                name='api_inbox'),
    path('messaging/sent/',              messaging.sent_items_view,           name='api_sent_items'), 
    path('messaging/unread/',            messaging.unread_message_count_view, name='api_unread_count'),
    path('messaging/employees/',         messaging.employee_list_view,        name='api_employee_list'),
    path('messaging/send/',              messaging.send_message_view,         name='api_send_message'),
    path('messaging/<int:msg_id>/read/', messaging.mark_message_read_view,    name='api_mark_read'),

    # ── Secondary Sales (Weekly Stockist Focus Products) ──────────────────────
    path('stock/pending-stockists/',     get_pending_stockists, name='api_pending_stockists'),
    path('stock/focus-products/',        get_focus_products,    name='api_focus_products'),
    path('stock/submit/',                submit_weekly_sales,   name='api_submit_stock'),
    path('stock/detail/',                get_weekly_sale_detail, name='api_weekly_sale_detail'),
    path('stock/history/',               weekly_sale_history,   name='api_weekly_sale_history'),
    path('stock/manage-focus-products/', api_rsm_manage_focus_products, name='api_manage_focus_products'),
]
