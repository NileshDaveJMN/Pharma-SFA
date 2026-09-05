"""
SFA/api/reports_helpers.py
===========================
Shared helper functions used across reports_core.py, reports_ops.py etc.
(reports.py se split kiya gaya — 1000+ line limit ke wajah se)
"""

"""
SFA/api/reports.py
===================
Flutter ke liye Reports REST API endpoints.

Endpoints (Phase 1 — priority reports):
    GET    /api/reports/product-sales/              → POB/Samples month-trend report
    GET    /api/reports/dcr/                         → DCR list (month-wise, with stats)
    GET    /api/reports/dcr/<int:dcr_id>/             → Ek single DCR ka full detail
    GET    /api/reports/approvals/                   → Manager Approval Hub — pending items
    POST   /api/reports/approvals/action/             → Approve/Reject action
    GET    /api/reports/network/                      → Doctor/Chemist network listing
    GET    /api/reports/products/                     → Product master list
    GET    /api/reports/doctor-visits/                → Doctor-wise visit history matrix

Flutter usage:
    headers: {'Authorization': 'Token $token', 'Content-Type': 'application/json'}

Common pattern: jahan bhi 'employee_id' query param diya jaaye, Manager/Admin
us team-member ka data dekh sakta hai (MR sirf apna khud ka). Agar nahi diya,
default apna khud ka (MR) ya pehla team-member (Manager) hota hai.
"""

import calendar
from collections import defaultdict
from datetime import datetime

from django.utils import timezone
from django.db.models import Sum, Count
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from SFA.models import (
    Employee, Doctor, Chemist, Product, DailyDCR, DCRVisit, DCRProductDetail,
    MonthlyTourProgram, MonthlyExpenseReport, Route, Holiday,
    MonthlyTargetMaster, LeaveApplication, LeaveBalance, DayStart, SystemSetting,
    FreeQtyClaimMaster, GiftCampaignPlan, ChemistEditRequest, DoctorEditRequest,
)
from SFA.services.team import (
    get_full_team_employees,
    get_team_territory_ids,
    get_team_requested_routes,
    get_dropdown_team,
)
from SFA.views.reports_approvals import _get_target_chain_starter


def _resolve_selected_employee(request, employee):
    """
    Common pattern: ?employee_id=<id> query param se "kiska data dekhna hai"
    resolve karta hai. MR ke liye hamesha khud, Manager ke liye default
    pehla team-member (agar param na diya ho).
    """
    team_employees = get_dropdown_team(employee, ordered=False)
    default_emp_id = str(employee.id)
    if employee.designation != 'MR':
        first_sub = team_employees.exclude(id=employee.id).first()
        if first_sub:
            default_emp_id = str(first_sub.id)

    selected_emp_id = request.GET.get('employee_id') or default_emp_id
    
    # 🌟 FIX: Multi-Company Data Leak Block (IDOR Prevention)
    # 1. Pehle ensure karo ki jo ID request mein aayi hai, wo usi company ki hai
    selected_emp = get_object_or_404(Employee, id=int(selected_emp_id), company=employee.company)
    
    # 2. Agar user Manager/Hierarchy wala hai (Admin chhodkar), toh check karo ki 
    #    kya wo selected employee uski team mein hai? Agar nahi hai, toh access deny!
    if employee.designation not in ['Admin', 'System Administrator', 'MR']:
        if selected_emp.id != employee.id and not team_employees.filter(id=selected_emp.id).exists():
            # Agar koi Manager dusre Manager ki team ka ID daal raha hai, toh usko uska default data hi dikhao
            selected_emp = employee
            
    return selected_emp, team_employees

def _employee_brief(emp):
    return {
        'id': emp.id,
        'name': emp.name,
        'designation': emp.designation,
        'hq': emp.headquarter.name if emp.headquarter_id else None,
    }


# ==============================================================================
# 📊 1. PRODUCT SALES REPORT (POB / Samples — month trend)
# ==============================================================================

