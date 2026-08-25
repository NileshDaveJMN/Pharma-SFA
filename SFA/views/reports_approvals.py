from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Sum

from SFA.models import (
    Employee, Doctor, Chemist, Route, Holiday, LeaveApplication,
    MonthlyTourProgram, MonthlyExpenseReport, MonthlyTargetMaster, 
    FreeQtyClaimMaster, GiftCampaignPlan, ChemistEditRequest, DoctorEditRequest,
    DailyDCR, DCRProductDetail, SystemNotification, PharmaActivity
)
from .auth import get_full_team_employees
from SFA.decorators import employee_required

# ==============================================================================
# 1. 🛡️ MANAGER APPROVAL HUB (Main Dashboard)
# ==============================================================================
def _get_target_chain_starter(target):
    if not target.territory_id:
        return None
    return Employee.objects.filter(headquarter_id=target.territory_id, is_active=True).first()

@employee_required
def manager_approval_hub(request, employee):
    manager = employee
    team_members = get_full_team_employees(manager).exclude(id=manager.id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        itype = request.POST.get('item_type')
        iid = request.POST.get('item_id')
        
        obj = None
        if itype == 'mtp': obj = get_object_or_404(MonthlyTourProgram, id=iid)
        elif itype == 'doctor': obj = get_object_or_404(Doctor, id=iid)
        elif itype == 'chemist': obj = get_object_or_404(Chemist, id=iid)
        elif itype == 'monthly_expense': obj = get_object_or_404(MonthlyExpenseReport, id=iid)
        elif itype == 'route': obj = get_object_or_404(Route, id=iid)
        elif itype == 'holiday': obj = get_object_or_404(Holiday, id=iid)
        elif itype == 'leave': obj = get_object_or_404(LeaveApplication, id=iid)
        elif itype == 'target': obj = get_object_or_404(MonthlyTargetMaster, id=iid)
        elif itype == 'free_claim': obj = get_object_or_404(FreeQtyClaimMaster, id=iid)
        elif itype == 'gift_campaign': obj = get_object_or_404(GiftCampaignPlan, id=iid)
        elif itype == 'chemist_edit': obj = get_object_or_404(ChemistEditRequest, id=iid)
        elif itype == 'doctor_edit': obj = get_object_or_404(DoctorEditRequest, id=iid)
        
        if obj and action in ['approve', 'reject']:
            if action == 'approve':
                if itype == 'free_claim':
                    if manager.designation in ['Admin', 'System Administrator']:
                        obj.status = 'Approved'; obj.admin_remark = request.POST.get('remark', '')
                    else:
                        m_list = list(obj.approved_by_managers)
                        if manager.id not in m_list: m_list.append(manager.id)
                        obj.approved_by_managers = m_list
                        obj.manager_remark = request.POST.get('remark', '')
                        chain_complete = True
                        curr = obj.employee.manager
                        while curr and curr.designation not in ['Admin', 'System Administrator']:
                            if curr.id not in obj.approved_by_managers:
                                chain_complete = False; break
                            curr = curr.manager
                        obj.status = 'Pending_Admin' if chain_complete else 'Pending_Manager'
                            
                elif itype == 'target':
                    if manager.designation in ['Admin', 'System Administrator']:
                        obj.status = 'Approved'
                    else:
                        m_list = list(obj.approved_by_managers)
                        if manager.id not in m_list: m_list.append(manager.id)
                        obj.approved_by_managers = m_list
                        chain_complete = True
                        chain_emp = _get_target_chain_starter(obj)
                        curr = chain_emp.manager if chain_emp else None
                        while curr and curr.designation not in ['Admin', 'System Administrator']:
                            if curr.id not in obj.approved_by_managers:
                                chain_complete = False; break
                            curr = curr.manager
                        obj.status = 'Pending_Admin' if chain_complete else 'Pending_Manager'

                elif itype == 'gift_campaign':
                    obj.status = 'Approved'; obj.manager_remark = request.POST.get('remark', '')
                    
                elif itype == 'chemist_edit':
                    obj.chemist.name = obj.req_name
                    obj.chemist.phone = obj.req_phone
                    obj.chemist.address = obj.req_address
                    if obj.req_territory: obj.chemist.territory = obj.req_territory
                    if obj.req_route: obj.chemist.route = obj.req_route
                    obj.chemist.save()
                    obj.status = 'Approved'
                    
                elif itype == 'doctor_edit':
                    obj.doctor.name = obj.req_name
                    if obj.req_degree: obj.doctor.degree = obj.req_degree
                    if obj.req_specialty: obj.doctor.specialty = obj.req_specialty
                    if obj.req_category: obj.doctor.category = obj.req_category
                    if obj.req_territory: obj.doctor.territory = obj.req_territory
                    if obj.req_route: obj.doctor.route = obj.req_route
                    obj.doctor.mobile = obj.req_mobile
                    obj.doctor.email = obj.req_email
                    obj.doctor.dob = obj.req_dob
                    obj.doctor.address = obj.req_address
                    obj.doctor.dom = obj.req_dom
                    obj.doctor.spouse_dob = obj.req_spouse_dob
                    if obj.req_vcard_photo: obj.doctor.vcard_photo = obj.req_vcard_photo
                    obj.doctor.residential_address = obj.req_residential_address
                    obj.doctor.child_1_dob = obj.req_child_1_dob
                    obj.doctor.child_2_dob = obj.req_child_2_dob
                    if obj.req_photo: obj.doctor.photo = obj.req_photo
                    obj.doctor.save()
                    obj.status = 'Approved'

                else:
                    obj.status = 'Approved'
                    if itype == 'leave' and obj.leave_type != 'LWP':
                        bal = LeaveBalance.objects.get(employee=obj.employee, year=obj.start_date.year)
                        if obj.leave_type == 'CL': bal.cl_used += obj.no_of_days
                        elif obj.leave_type == 'SL': bal.sl_used += obj.no_of_days
                        elif obj.leave_type == 'PL': bal.pl_used += obj.no_of_days
                        bal.save()
                        
            else:
                obj.status = 'Rejected'
                if itype == 'free_claim':
                    if manager.designation in ['Admin', 'System Administrator']: obj.admin_remark = request.POST.get('remark', '')
                    else: obj.manager_remark = request.POST.get('remark', '')
                elif itype == 'gift_campaign':
                    obj.manager_remark = request.POST.get('remark', '')
            
            obj.save()

            try:
                if itype == 'target':
                    applicant = _get_target_chain_starter(obj)
                else:
                    applicant = getattr(obj, 'employee', getattr(obj, 'requested_by', getattr(obj, 'proposed_by', getattr(obj, 'allocated_to', None))))
                if applicant:
                    formatted_type = itype.replace('_', ' ').title()
                    msg = f"Your {formatted_type} has been {obj.status} by {manager.name}."
                    SystemNotification.objects.create(
                        employee=applicant, 
                        title=f"{formatted_type} {obj.status}!", 
                        message=msg
                    )
            except Exception: pass 
            
            return redirect('manager_approvals')

    pending_targets, pending_free_claims, pending_gift_campaigns = [], [], []

    if manager.designation in ['Admin', 'System Administrator']:
        pt_admin = MonthlyTargetMaster.objects.filter(territory__company=employee.company).exclude(status__in=['Draft', 'Approved', 'Rejected']).order_by('-year', '-month')
        for t in pt_admin:
            if t.status == 'Pending_Admin': pending_targets.append(t)
            else:
                chain_approved = True
                chain_emp = _get_target_chain_starter(t)
                curr = chain_emp.manager if chain_emp else None
                while curr and curr.designation not in ['Admin', 'System Administrator']:
                    if curr.id not in t.approved_by_managers: chain_approved = False; break
                    curr = curr.manager
                if chain_approved and t not in pending_targets: pending_targets.append(t)

        fc_admin = FreeQtyClaimMaster.objects.filter(employee__company=employee.company).exclude(status__in=['Draft', 'Approved', 'Rejected']).order_by('created_at')
        for c in fc_admin:
            if c.status == 'Pending_Admin': pending_free_claims.append(c)
            else:
                chain_approved = True
                curr = c.employee.manager
                while curr and curr.designation not in ['Admin', 'System Administrator']:
                    if curr.id not in c.approved_by_managers: chain_approved = False; break
                    curr = curr.manager
                if chain_approved and c not in pending_free_claims: pending_free_claims.append(c)

        pending_gift_campaigns = GiftCampaignPlan.objects.filter(employee__in=team_members, status='Pending').select_related('employee', 'doctor', 'item').order_by('-id')

    else:
        team_territories = Employee.objects.filter(id__in=team_members).exclude(headquarter__isnull=True).values_list('headquarter_id', flat=True)
        pt = MonthlyTargetMaster.objects.filter(territory_id__in=team_territories, status='Pending_Manager').order_by('-year', '-month')

        for t in pt:
            if manager.id in t.approved_by_managers: continue
            chain_approved = True
            chain_emp = _get_target_chain_starter(t)
            curr = chain_emp.manager if chain_emp else None
            while curr and curr.id != manager.id:
                if curr.id not in t.approved_by_managers: chain_approved = False; break
                curr = curr.manager
            if chain_approved: pending_targets.append(t)
                
        pfc = FreeQtyClaimMaster.objects.filter(employee__in=team_members, status='Pending_Manager').order_by('created_at')
        for c in pfc:
            if manager.id in c.approved_by_managers: continue
            chain_approved = True
            curr = c.employee.manager
            while curr and curr.id != manager.id:
                if curr.id not in c.approved_by_managers: chain_approved = False; break
                curr = curr.manager
            if chain_approved: pending_free_claims.append(c)

        pending_gift_campaigns = list(GiftCampaignPlan.objects.filter(employee__in=team_members, status='Pending').select_related('employee', 'doctor', 'item'))

    return render(request, 'manager_approvals.html', {
        'pending_mtps': MonthlyTourProgram.objects.filter(employee__in=team_members, status='Pending').order_by('-year', '-month'),
        'pending_doctors': Doctor.objects.filter(allocated_to__in=team_members, status='Pending'),
        'pending_chemists': Chemist.objects.filter(allocated_to__in=team_members, status='Pending'),
        'pending_expenses': MonthlyExpenseReport.objects.filter(employee__in=team_members, status='Pending'),
        'pending_routes': Route.objects.filter(requested_by__in=team_members, status='Pending').select_related('territory', 'requested_by'),
        'pending_holidays': Holiday.objects.filter(company=employee.company, status='Pending') if manager.designation in ['Admin', 'System Administrator'] else [], 
        'pending_targets': pending_targets,
        'pending_free_claims': pending_free_claims,
        'pending_chemist_edits': ChemistEditRequest.objects.filter(employee__in=team_members, status='Pending'),
        'pending_doctor_edits': DoctorEditRequest.objects.filter(employee__in=team_members, status='Pending'),
        'pending_gift_campaigns': pending_gift_campaigns,
        'manager_name': manager.name, 'designation': manager.designation,
        'pending_leaves': LeaveApplication.objects.filter(employee__in=team_members, status='Pending').order_by('start_date'),
    })

# ==============================================================================
# 2. 📊 MANAGER REPORT VIEW (Daily Summary)
# ==============================================================================
@employee_required
def manager_report_view(request, employee):
    today = timezone.localdate()
    mr_reports = DailyDCR.objects.filter(employee__company=employee.company, date=today).select_related('employee').annotate(
        total_visits=Count('visits', distinct=True), total_samples=Sum('visits__product_details__sample_qty'), total_orders=Sum('visits__product_details__order_qty')
    ).values('employee__name', 'total_visits', 'total_samples', 'total_orders')
    grand_total_orders = DCRProductDetail.objects.filter(visit__daily_dcr__employee__company=employee.company, visit__daily_dcr__date=today).aggregate(total=Sum('order_qty'))['total'] or 0
    return render(request, 'manager_report.html', {'today': today, 'mr_reports': mr_reports, 'grand_total_orders': grand_total_orders})

# ==============================================================================
# 3. 📝 REVIEW MTP VIEW
# ==============================================================================
def send_auto_alert(employee, title, message):
    if employee:
        SystemNotification.objects.create(employee=employee, title=title, message=message)

@employee_required
def review_mtp_view(request, employee, mtp_id):
    manager = employee
    mtp = get_object_or_404(MonthlyTourProgram, id=mtp_id)
    
    if mtp.employee not in get_full_team_employees(manager) and manager.designation != 'NSM': 
        return redirect('manager_approvals')
        
    daily_plans = mtp.daily_plans.all().order_by('date')
    
    if request.method == "POST":
        action = request.POST.get('action')
        remark = request.POST.get('manager_remark', '').strip()
        
        if action == 'Reject': 
            mtp.status = 'Rejected'
            mtp.manager_remark = remark
            mtp.save()
            
            send_auto_alert(mtp.employee, "Tour Plan Rejected ❌", f"Your Tour Plan for {mtp.month}/{mtp.year} has been rejected by {manager.name}.")
            if manager.manager:
                send_auto_alert(manager.manager, "Team MTP Action 📊", f"{manager.name} has rejected the Tour Plan of {mtp.employee.name} for {mtp.month}/{mtp.year}.")
                
            return redirect('manager_approvals')
            
        elif action == 'Approve':
            is_changed = False
            for dp in daily_plans:
                new_route_id = request.POST.get(f'route_{dp.id}')
                if new_route_id and int(new_route_id) != dp.route_id: 
                    dp.route_id = new_route_id
                    dp.save()
                    is_changed = True
                    
            mtp.status = 'Approved'
            mtp.manager_remark = remark
            mtp.is_modified = is_changed
            mtp.save()
            
            send_auto_alert(mtp.employee, "Tour Plan Approved ✅", f"Your Tour Plan for {mtp.month}/{mtp.year} has been approved by {manager.name}.")
            if manager.manager:
                send_auto_alert(manager.manager, "Team MTP Action 📊", f"{manager.name} has approved the Tour Plan of {mtp.employee.name} for {mtp.month}/{mtp.year}.")
                
            return redirect('manager_approvals')
            
    return render(request, 'review_mtp.html', {'mtp': mtp, 'daily_plans': daily_plans, 'all_routes': Route.objects.filter(company=employee.company)})

# ==============================================================================
# 4. 🏥 APPROVE PHARMA ACTIVITY
# ==============================================================================
@employee_required
def approve_activity_view(request, employee, activity_id):
    activity = get_object_or_404(PharmaActivity, id=activity_id)
    if request.method == "POST":
        action, remark = request.POST.get('action'), request.POST.get('remark', '')
        if action == 'Reject': 
            activity.status = 'Rejected'
            activity.manager_remark = remark
            activity.save()
            messages.error(request, "Activity rejected.")
            return redirect('manager_approvals')
        elif action == 'Approve':
            chain_managers, creator_manager = [], activity.employee.manager
            while creator_manager is not None: 
                chain_managers.append(creator_manager.id)
                creator_manager = creator_manager.manager
            if employee.id in chain_managers:
                if employee.id not in activity.approved_by_managers: 
                    activity.approved_by_managers.append(employee.id)
                if len(activity.approved_by_managers) >= len(chain_managers): 
                    activity.status = 'Pending_Admin'
                    messages.success(request, "Approved by all managers! Pending Admin Approval.")
                else: 
                    messages.info(request, "Your approval has been recorded.")
                activity.save()
    return redirect('manager_approvals')
