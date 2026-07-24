"""
SFA/api/reports_approvals.py
=============================
Manager Approval Hub — pending list + approve/reject action.
(reports.py se split kiya gaya — 1000+ line limit ke wajah se)
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
from SFA.views.reports import _get_target_chain_starter


def _chain_approved_for_target(target, manager):
    """Target approval-chain check — _get_target_chain_starter reuse karke."""
    chain_emp = _get_target_chain_starter(target)
    curr = chain_emp.manager if chain_emp else None
    while curr and curr.id != manager.id and curr.designation not in ('Admin', 'System Administrator'):
        if curr.id not in target.approved_by_managers:
            return False
        curr = curr.manager
    return True


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_approval_hub(request):
    """
    Manager/Admin ke saare PENDING approval-items, category-wise.
    (MTP, Doctor, Chemist, Expense, Route, Holiday, Leave, Target,
    Free Claim, Gift Campaign, Doctor Edit, Chemist Edit)

    Response:
    {
        "manager_name": "Suresh RBM", "designation": "RBM",
        "pending": {
            "mtp": [{"id": 5, "employee": "Amit MR", "month": 6, "year": 2026}],
            "doctors": [{"id": 12, "name": "Dr. Sharma", "employee": "Amit MR"}],
            "chemists": [...],
            "expenses": [{"id": 7, "employee": "Amit MR", "month": 6, "year": 2026}],
            "routes": [{"id": 3, "name": "Dadar West", "requested_by": "Amit MR"}],
            "holidays": [{"id": 1, "name": "Diwali", "date": "2026-11-01"}],
            "leaves": [{"id": 9, "employee": "Amit MR", "leave_type": "CL", "start_date": "...", "end_date": "...", "days": 2}],
            "targets": [{"id": 4, "territory": "Dadar", "month": 6, "year": 2026}],
            "free_claims": [{"id": 8, "employee": "Amit MR", "stockist": "ABC Pharma", "month": 6, "year": 2026}],
            "gift_campaigns": [{"id": 2, "employee": "Amit MR", "doctor": "Dr. Sharma", "item": "Diary"}],
            "doctor_edits": [{"id": 6, "doctor": "Dr. Sharma", "employee": "Amit MR"}],
            "chemist_edits": [...]
        }
    }
    """
    try:
        manager = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    team_members = get_full_team_employees(manager).exclude(id=manager.id)
    is_admin = manager.designation in ('Admin', 'System Administrator')

    pending_targets, pending_free_claims = [], []

    if is_admin:
        pt_admin = MonthlyTargetMaster.objects.exclude(status__in=['Draft', 'Approved', 'Rejected']).filter(territory__company=manager.company).order_by('-year', '-month')

        for t in pt_admin:
            if t.status == 'Pending_Admin' or _chain_approved_for_target(t, manager):
                pending_targets.append(t)

        fc_admin = FreeQtyClaimMaster.objects.exclude(status__in=['Draft', 'Approved', 'Rejected']).filter(employee__company=manager.company).order_by('created_at')
        for c in fc_admin:
            if c.status == 'Pending_Admin':
                pending_free_claims.append(c)
            else:
                chain_approved = True
                curr = c.employee.manager
                while curr and curr.designation not in ('Admin', 'System Administrator'):
                    if curr.id not in c.approved_by_managers:
                        chain_approved = False
                        break
                    curr = curr.manager
                if chain_approved:
                    pending_free_claims.append(c)

        pending_gift_campaigns = GiftCampaignPlan.objects.filter(
            employee__in=team_members, status='Pending'
        ).select_related('employee', 'doctor', 'item')
        pending_holidays = Holiday.objects.filter(proposed_by__in=team_members, status='Pending')  # 🌟 FIX: pehle poore system ke pending holidays dikhte the, ab sirf apni team ke
    else:
        team_territories = Employee.objects.filter(id__in=team_members).exclude(
            headquarter__isnull=True
        ).values_list('headquarter_id', flat=True)

        pt = MonthlyTargetMaster.objects.filter(territory_id__in=team_territories, status='Pending_Manager').order_by('-year', '-month')
        for t in pt:
            if manager.id not in t.approved_by_managers and _chain_approved_for_target(t, manager):
                pending_targets.append(t)

        pfc = FreeQtyClaimMaster.objects.filter(employee__in=team_members, status='Pending_Manager').order_by('created_at')
        for c in pfc:
            if manager.id in c.approved_by_managers:
                continue
            chain_approved = True
            curr = c.employee.manager
            while curr and curr.id != manager.id:
                if curr.id not in c.approved_by_managers:
                    chain_approved = False
                    break
                curr = curr.manager
            if chain_approved:
                pending_free_claims.append(c)

        pending_gift_campaigns = GiftCampaignPlan.objects.filter(
            employee__in=team_members, status='Pending'
        ).select_related('employee', 'doctor', 'item')
        pending_holidays = []

    pending_mtps = MonthlyTourProgram.objects.filter(employee__in=team_members, status='Pending').select_related('employee').order_by('-year', '-month')
    pending_doctors = Doctor.objects.filter(allocated_to__in=team_members, status='Pending').select_related('allocated_to')
    pending_chemists = Chemist.objects.filter(allocated_to__in=team_members, status='Pending').select_related('allocated_to')
    pending_expenses = MonthlyExpenseReport.objects.filter(employee__in=team_members, status='Pending').select_related('employee')
    pending_routes = Route.objects.filter(requested_by__in=team_members, status='Pending').select_related('territory', 'requested_by')
    pending_leaves = LeaveApplication.objects.filter(employee__in=team_members, status='Pending').select_related('employee').order_by('start_date')
    pending_chemist_edits = ChemistEditRequest.objects.filter(employee__in=team_members, status='Pending').select_related('employee', 'chemist')
    pending_doctor_edits = DoctorEditRequest.objects.filter(employee__in=team_members, status='Pending').select_related('employee', 'doctor')

    return Response({
        'manager_name': manager.name,
        'designation': manager.designation,
        'pending': {
            'mtp': [
                {'id': m.id, 'employee': m.employee.name, 'month': m.month, 'year': m.year}
                for m in pending_mtps
            ],
            'doctors': [
                {'id': d.id, 'name': d.name, 'employee': d.allocated_to.name if d.allocated_to else None}
                for d in pending_doctors
            ],
            'chemists': [
                {'id': c.id, 'name': c.name, 'employee': c.allocated_to.name if c.allocated_to else None}
                for c in pending_chemists
            ],
            'expenses': [
                {'id': e.id, 'employee': e.employee.name, 'month': e.month, 'year': e.year}
                for e in pending_expenses
            ],
            'routes': [
                {'id': r.id, 'name': r.name, 'requested_by': r.requested_by.name if r.requested_by else None}
                for r in pending_routes
            ],
            'holidays': [
                {'id': h.id, 'name': h.name, 'date': str(h.date)}
                for h in pending_holidays
            ],
            'leaves': [
                {
                    'id': l.id, 'employee': l.employee.name, 'leave_type': l.leave_type,
                    'start_date': str(l.start_date), 'end_date': str(l.end_date),
                    'days': l.no_of_days, 'reason': l.reason,
                } for l in pending_leaves
            ],
            'targets': [
                {
                    'id': t.id,
                    'territory': t.territory.name if t.territory_id else None,
                    'month': t.month, 'year': t.year, 'status': t.status,
                } for t in pending_targets
            ],
           'free_claims': [
                {
                    'id': c.id, 'employee': c.employee.name,
                    'stockist': c.stockist.name if c.stockist_id else None,
                    'month': c.month, 'year': c.year, 'status': c.status,
                    # 🌟 NAYA FIX: Andar ke products aur unki value bhi bhej rahe hain
                    'lines': [
                        {
                            'product_name': line.product.name,
                            'billed_qty': line.total_billed_qty,
                            'free_qty': line.total_free_qty,
                            'value': float(line.claim_value)
                        } for line in c.claim_lines.all()
                    ],
                    'grand_total': sum(float(line.claim_value) for line in c.claim_lines.all())
                } for c in pending_free_claims
            ],
            'gift_campaigns': [
                {
                    'id': g.id, 'employee': g.employee.name,
                    'doctor': g.doctor.name if g.doctor_id else None,
                    'item': g.item.name if g.item_id else None,
                    'month': g.month, 'year': g.year,
                } for g in pending_gift_campaigns
            ],
            'doctor_edits': [
                {
                    'id': e.id, 'employee': e.employee.name,
                    'doctor_id': e.doctor.id,
                    'original': {
                        'name': e.doctor.name, 'degree': e.doctor.degree, 'specialty': e.doctor.specialty,
                        'category': e.doctor.category, 'mobile': e.doctor.mobile, 'email': e.doctor.email,
                        'dob': str(e.doctor.dob) if e.doctor.dob else None,
                        'territory': e.doctor.territory.name if e.doctor.territory_id else None,
                        'route': e.doctor.route.name if e.doctor.route_id else None,
                        'address': e.doctor.address,
                    },
                    'requested': {
                        'name': e.req_name, 'degree': e.req_degree, 'specialty': e.req_specialty,
                        'category': e.req_category, 'mobile': e.req_mobile, 'email': e.req_email,
                        'dob': str(e.req_dob) if e.req_dob else None,
                        'territory': e.req_territory.name if e.req_territory_id else None,
                        'route': e.req_route.name if e.req_route_id else None,
                        'address': e.req_address,
                    },
                } for e in pending_doctor_edits
            ],
            'chemist_edits': [
                {
                    'id': e.id, 'employee': e.employee.name,
                    'chemist_id': e.chemist.id,
                    'original': {
                        'name': e.chemist.name, 'phone': e.chemist.phone, 'address': e.chemist.address,
                        'territory': e.chemist.territory.name if e.chemist.territory_id else None,
                        'route': e.chemist.route.name if e.chemist.route_id else None,
                    },
                    'requested': {
                        'name': e.req_name, 'phone': e.req_phone, 'address': e.req_address,
                        'territory': e.req_territory.name if e.req_territory_id else None,
                        'route': e.req_route.name if e.req_route_id else None,
                    },
                } for e in pending_chemist_edits
            ],
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_approval_action(request):
    """
    Approve/Reject action — web ke manager_approval_hub jaisa hi logic,
    REST se. Notification system bhi same (SystemNotification).

    POST body (JSON):
    {
        "item_type": "leave",     // mtp|doctor|chemist|monthly_expense|route|
                                   // holiday|leave|target|free_claim|
                                   // gift_campaign|chemist_edit|doctor_edit
        "item_id": 9,
        "action": "approve",      // approve | reject
        "remark": "OK approved"   // optional, free_claim/gift_campaign use karte hain
    }

    Success (200): { "message": "Approved successfully", "new_status": "Approved" }
    Error (400): { "error": "..." }
    """
    try:
        manager = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    itype = request.data.get('item_type')
    iid = request.data.get('item_id')
    action = request.data.get('action')
    remark = request.data.get('remark', '')

    if action not in ('approve', 'reject'):
        return Response({'error': "action 'approve' ya 'reject' hona chahiye"}, status=400)

    MODEL_MAP = {
        'mtp': MonthlyTourProgram, 'doctor': Doctor, 'chemist': Chemist,
        'monthly_expense': MonthlyExpenseReport, 'route': Route, 'holiday': Holiday,
        'leave': LeaveApplication, 'target': MonthlyTargetMaster,
        'free_claim': FreeQtyClaimMaster, 'gift_campaign': GiftCampaignPlan,
        'chemist_edit': ChemistEditRequest, 'doctor_edit': DoctorEditRequest,
    }
    model = MODEL_MAP.get(itype)
    if not model:
        return Response({'error': f"Invalid item_type: {itype}"}, status=400)

    obj = get_object_or_404(model, id=iid)
    is_admin = manager.designation in ('Admin', 'System Administrator')

    # 🌟 FIX: IDOR Attack Block — Cross-company approval/reject rokna
    target_emp = None
    if itype in ['mtp', 'monthly_expense', 'leave', 'free_claim', 'gift_campaign', 'doctor_edit', 'chemist_edit']:
        target_emp = getattr(obj, 'employee', None)
    elif itype in ['doctor', 'chemist']:
        target_emp = getattr(obj, 'allocated_to', None)
    elif itype == 'route':
        target_emp = getattr(obj, 'requested_by', None)
    elif itype == 'holiday':
        target_emp = getattr(obj, 'proposed_by', None)
    
    # Agar object kisika hai, toh check karo ki wo usi company ka hai ya nahi
    if target_emp and target_emp.company_id != manager.company_id:
        return Response({'error': 'Access denied: You cannot approve/reject items from another company.'}, status=403)
        
    # Target object mein employee nahi hota, usme territory hota hai
    if itype == 'target' and hasattr(obj, 'territory') and obj.territory.company_id != manager.company_id:
        return Response({'error': 'Access denied: You cannot approve/reject items from another company.'}, status=403)

    if action == 'approve':
        if itype == 'free_claim':
            if is_admin:
                obj.status = 'Approved'
                obj.admin_remark = remark
            else:
                m_list = list(obj.approved_by_managers)
                if manager.id not in m_list:
                    m_list.append(manager.id)
                obj.approved_by_managers = m_list
                obj.manager_remark = remark
                chain_complete = True
                curr = obj.employee.manager
                while curr and curr.designation not in ('Admin', 'System Administrator'):
                    if curr.id not in obj.approved_by_managers:
                        chain_complete = False
                        break
                    curr = curr.manager
                obj.status = 'Pending_Admin' if chain_complete else 'Pending_Manager'

        elif itype == 'target':
            if is_admin:
                obj.status = 'Approved'
            else:
                m_list = list(obj.approved_by_managers)
                if manager.id not in m_list:
                    m_list.append(manager.id)
                obj.approved_by_managers = m_list
                chain_complete = True
                chain_emp = _get_target_chain_starter(obj)
                curr = chain_emp.manager if chain_emp else None
                while curr and curr.designation not in ('Admin', 'System Administrator'):
                    if curr.id not in obj.approved_by_managers:
                        chain_complete = False
                        break
                    curr = curr.manager
                obj.status = 'Pending_Admin' if chain_complete else 'Pending_Manager'

        elif itype == 'gift_campaign':
            obj.status = 'Approved'
            obj.manager_remark = remark

        elif itype == 'chemist_edit':
            obj.chemist.name = obj.req_name
            obj.chemist.phone = obj.req_phone
            obj.chemist.address = obj.req_address  # 🌟 FIX: address copy missing thi (views ke saath sync)
            if obj.req_territory:
                obj.chemist.territory = obj.req_territory
            if obj.req_route:
                obj.chemist.route = obj.req_route
            obj.chemist.save()
            obj.status = 'Approved'

        elif itype == 'doctor_edit':
            obj.doctor.name = obj.req_name
            if obj.req_degree:
                obj.doctor.degree = obj.req_degree
            if obj.req_specialty:
                obj.doctor.specialty = obj.req_specialty
            if obj.req_category:
                obj.doctor.category = obj.req_category
            if obj.req_territory:
                obj.doctor.territory = obj.req_territory
            if obj.req_route:
                obj.doctor.route = obj.req_route
            obj.doctor.mobile = obj.req_mobile
            obj.doctor.email = obj.req_email
            obj.doctor.dob = obj.req_dob
            obj.doctor.address = obj.req_address
            obj.doctor.dom = obj.req_dom
            obj.doctor.spouse_dob = obj.req_spouse_dob
            if obj.req_vcard_photo:
                obj.doctor.vcard_photo = obj.req_vcard_photo
            obj.doctor.residential_address = obj.req_residential_address
            obj.doctor.child_1_dob = obj.req_child_1_dob
            obj.doctor.child_2_dob = obj.req_child_2_dob
            if obj.req_photo:
                obj.doctor.photo = obj.req_photo
            obj.doctor.save()
            obj.status = 'Approved'

        else:
            obj.status = 'Approved'
            if itype == 'leave' and obj.leave_type != 'LWP':
                bal = LeaveBalance.objects.get(employee=obj.employee, year=obj.start_date.year)
                if obj.leave_type == 'CL':
                    bal.cl_used += obj.no_of_days
                elif obj.leave_type == 'SL':
                    bal.sl_used += obj.no_of_days
                elif obj.leave_type == 'PL':
                    bal.pl_used += obj.no_of_days
                bal.save()
    else:
        obj.status = 'Rejected'
        if itype == 'free_claim':
            if is_admin:
                obj.admin_remark = remark
            else:
                obj.manager_remark = remark
        elif itype == 'gift_campaign':
            obj.manager_remark = remark

    obj.save()

    # 🔔 Notification — same as web version
    try:
        from SFA.models import SystemNotification
        if itype == 'target':
            applicant = _get_target_chain_starter(obj)
        else:
            applicant = getattr(obj, 'employee', getattr(obj, 'requested_by', getattr(obj, 'proposed_by', getattr(obj, 'allocated_to', None))))
        if applicant:
            formatted_type = itype.replace('_', ' ').title()
            SystemNotification.objects.create(
                employee=applicant,
                title=f"{formatted_type} {obj.status}!",
                message=f"Aapka {formatted_type} {manager.name} ne {obj.status} kar diya hai.",
            )
    except Exception:
        pass

    return Response({'message': f'{action.title()}d successfully', 'new_status': obj.status})


# ==============================================================================
# 🩺 4. NETWORK REPORT (Doctor / Chemist listing)
# ==============================================================================

