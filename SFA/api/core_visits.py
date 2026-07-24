"""
SFA/api/core_visits.py
=======================
Doctor visit detail/edit/delete endpoints.
(core.py se split kiya gaya — 1000+ line limit ke wajah se)
"""

import calendar
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Q

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from SFA.models import (
    Employee, Doctor, Chemist, Route, Territory, DailyTourPlan,
    DayStart, DayEnd, DailyDCR, DCRVisit, DCRProductDetail, Product, MRInventory,
    DailyDCRStatus, LeaveApplication, Holiday,
    MonthlyTourProgram, MonthlyExpenseReport, PartyWiseSaleReport,
    MonthlyTargetMaster, FreeQtyClaimMaster, GiftCampaignPlan,
    SystemSetting, CompanyNotice, DailyExpense, DARate, TARate, HQDistance,
    SystemNotification, DirectMessage, DoctorEditRequest, ChemistEditRequest, LeaveBalance
)

from SFA.services.team import (
    get_full_team_employees,
    get_team_territory_ids,
    get_team_route_ids,
)
from SFA.views.core import sync_dcr_calendar, get_open_day, _normalize_status

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_doctor_visit_detail(request, visit_id):
    # 🌟 FIX: employee direct field nahi hai, daily_dcr ke through aata hai
    try:
        visit = DCRVisit.objects.get(id=visit_id, daily_dcr__employee=request.user.employee)
    except DCRVisit.DoesNotExist:
        return Response({'error': 'Visit not found.'}, status=404)    

    # 🗑️ DELETE VISIT
    if request.method == 'DELETE':
        visit.delete()
        return Response({'message': 'Visit deleted successfully.'}, status=200)

    # 📥 GET VISIT (For Pre-filling Edit Form)
    if request.method == 'GET':
        # Yahan aapko products aur gifts ka waisa hi JSON bhejna hai jaisa normal visit form mein bhejte hain,
        # Bas isme 'selected_sample_qty', 'selected_order_qty' pre-filled bhejni hogi.
        data = {
            'doctor_name': visit.doctor.name,
            'remark': visit.remark,
            'products': [
                {
                    'id': p.product.id,
                    'name': p.product.name,
                    'sample_stock': p.product.current_stock, 
                    'selected_sample_qty': p.sample_qty,  # Pre-fill value
                    'selected_order_qty': p.order_qty,    # Pre-fill value
                    'is_detailed': p.is_detailed
                } for p in visit.visit_products.all()
            ],
            # Same logic for gifts...
        }
        return Response(data, status=200)

    # 📤 UPDATE VISIT (PUT)
    if request.method == 'PUT':
        data = request.data
        visit.remark = data.get('remark', visit.remark)
        visit.save()
        
        # Yahan existing products delete karke naye add karne ka logic ya update karne ka logic likhein
        # ...
        
        return Response({'message': 'Visit updated successfully.'}, status=200)

# ==============================================================================
# 📊 DASHBOARD
# ==============================================================================



@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_delete_visit(request, visit_id):
    employee = request.user.employee
    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee)
    visit_date = visit.daily_dcr.date
    
    # Block deletion if the day is already closed
    if DayEnd.objects.filter(employee=employee, date=visit_date, is_closed=True).exists():
        return Response({'error': 'Cannot delete visit. Day End has already been submitted.'}, status=403)
        
    customer_name = visit.doctor.name if visit.doctor else visit.chemist.name
    
    # DCRProductDetail records are automatically removed via models.CASCADE
    visit.delete()
    
    return Response({'message': f'Visit for {customer_name} has been deleted successfully.'})

# ==============================================================================
# 📢 NOTICES
# ==============================================================================



@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def api_edit_visit(request, visit_id):
    employee = request.user.employee
    visit = get_object_or_404(DCRVisit, id=visit_id, daily_dcr__employee=employee)
    visit_date = visit.daily_dcr.date
    
    if DayEnd.objects.filter(employee=employee, date=visit_date, is_closed=True).exists():
        return Response({'success': False, 'error': 'Ye visit lock ho gayi hai, ab edit nahi ho sakti.'}, status=403)

    if request.method == 'GET':
        ed = {d.product_id: d for d in DCRProductDetail.objects.filter(visit=visit)}
        
        # 🌟 NAYA: Inventory Stock Check
        my_inv = MRInventory.objects.filter(employee=employee, item__item_type='Sample')
        inv_map = {inv.item.linked_product_id: inv.stock_qty for inv in my_inv if inv.item.linked_product_id}
        
        products_data = []
        for p in Product.objects.filter(company=employee.company):  # 🌟 FIX: company-scoped
            old_qty = ed[p.id].sample_qty if p.id in ed else 0
            curr_stock = inv_map.get(p.id, 0)
            max_allowed = curr_stock + old_qty # (MR ke bag ka stock + jo is visit mein pehle diya tha)
            
            products_data.append({
                'product_id': p.id, 
                'product_name': p.name,
                'is_detailed': ed[p.id].is_detailed if p.id in ed else False,
                'sample_qty': old_qty,
                'order_qty': ed[p.id].order_qty if p.id in ed else 0,
                'max_sample_qty': max_allowed # 🌟 FLUTTER KO BHEJ RAHE HAIN
            })
            
        return Response({
            'success': True, 'customer_name': visit.doctor.name if visit.doctor else visit.chemist.name,
            'customer_type': 'Doctor' if visit.doctor else 'Chemist', 'remark': visit.remark, 'products': products_data
        })

    if request.method == 'PUT':
        visit.remark = request.data.get('remark', '')
        visit.save()
        
        products_payload = request.data.get('products', [])
        for p_data in products_payload:
            p_id = p_data.get('product_id')
            is_det = p_data.get('is_detailed', False)
            new_sq = int(p_data.get('sample_qty', 0))
            oq = int(p_data.get('order_qty', 0))
            
            # 🌟 FIX: Sirf usi company ka product allow karo
            p = get_object_or_404(Product, id=p_id, company=employee.company)
            old_sq = 0
            
            d = DCRProductDetail.objects.filter(visit=visit, product=p).first()
            if d:
                old_sq = d.sample_qty or 0
                if is_det or new_sq > 0 or oq > 0:
                    d.is_detailed, d.sample_qty, d.order_qty = is_det, new_sq, oq
                    d.save()
                else:
                    d.delete()
            else:
                if is_det or new_sq > 0 or oq > 0:
                    DCRProductDetail.objects.create(visit=visit, product=p, is_detailed=is_det, sample_qty=new_sq, order_qty=oq)
            
            # 🌟 NAYA: DYNAMIC INVENTORY ADJUSTMENT
            diff = new_sq - old_sq
            if diff != 0:
                inv = MRInventory.objects.filter(employee=employee, item__linked_product=p, item__item_type='Sample').first()
                if inv:
                    inv.stock_qty -= diff
                    inv.save()
                    
        return Response({'success': True, 'message': 'Visit successfully updated!'})

# ==============================================================================
# 🪑 VACANCIES
# ==============================================================================
