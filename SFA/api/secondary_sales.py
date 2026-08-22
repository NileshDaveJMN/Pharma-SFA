import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from SFA.services.team import get_dropdown_team

from SFA.models import (
    Stockist, 
    FocusProductTracking, 
    WeeklyStockistSaleMaster, 
    WeeklyStockistSaleDetail,
    Product,
    CampaignControl
)

# ==============================================================================
# 1. API to get list of Stockists and their submission status (For MR)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pending_stockists(request):
    try:
        employee = request.user.employee
        company = employee.company
        
        # Flutter app will pass the Saturday date it is asking for
        # e.g., /api/stock/pending-stockists/?date=2026-08-08
        target_date = request.query_params.get('date')
        if not target_date:
            return Response({'status': 'error', 'message': 'Date parameter is required.'}, status=400)
            
        stockists = Stockist.objects.filter(territory=employee.headquarter, company=company)
        
        # Fetch IDs of stockists whose data is already submitted for this date
        submitted_ids = WeeklyStockistSaleMaster.objects.filter(
            employee=employee, week_ending_date=target_date
        ).values_list('stockist_id', flat=True)
        
        data = []
        for s in stockists:
            data.append({
                'id': s.id,
                'name': s.name,
                'status': 'Submitted' if s.id in submitted_ids else 'Pending'
            })
            
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# 2. API to get the list of active Focus Products (For MR)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_focus_products(request):
    try:
        employee = request.user.employee
        company = employee.company
        
        active_focus = FocusProductTracking.objects.filter(company=company, is_active=True)
        data = []
        for f in active_focus:
            data.append({
                'product_id': f.product.id,
                'name': f.product.name,
                'pack_size': f.product.pack_size,
            })
            
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# 3. API to Submit the Weekly Sales Data (For MR)
# ==============================================================================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_weekly_sales(request):
    try:
        employee = request.user.employee
        company = employee.company
        data = request.data  # DRF automatically parses JSON body
        
        stockist_id = data.get('stockist_id')
        week_ending_date = data.get('week_ending_date') # Flutter will send this
        total_sec = data.get('total_sec_sale_value', 0)
        total_close = data.get('total_closing_value', 0)
        items = data.get('items', []) # [{'product_id': 1, 'sec_sale_qty': 10, 'closing_qty': 50}]
        
        if not week_ending_date:
            return Response({'status': 'error', 'message': 'week_ending_date is required.'}, status=400)
        
        # update_or_create allows MRs to edit their mistakes if they resubmit
        master, created = WeeklyStockistSaleMaster.objects.update_or_create(
            company=company,
            stockist_id=stockist_id,
            week_ending_date=week_ending_date,
            defaults={
                'employee': employee,
                'total_sec_sale_value': total_sec,
                'total_closing_value': total_close
            }
        )
        
        # Delete old details for this specific week to avoid duplicate additions on edit
        WeeklyStockistSaleDetail.objects.filter(master=master).delete()
        
        # Save new focus product details
        for item in items:
            sec_qty = item.get('sec_sale_qty', 0)
            closing_qty = item.get('closing_qty', 0)
            
            # Only save if they entered qty greater than 0
            if int(sec_qty) > 0 or int(closing_qty) > 0:
                WeeklyStockistSaleDetail.objects.create(
                    master=master,
                    product_id=item['product_id'],
                    sec_sale_qty=sec_qty,
                    closing_qty=closing_qty
                )
                
        return Response({'status': 'success', 'message': 'Weekly Sales saved successfully!'})
        
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# 4. API for RSM to Manage Focus Products & Campaign (For Manager Mobile App)
# ==============================================================================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_rsm_manage_focus_products(request):
    employee = request.user.employee
    company = employee.company

    # Allowed Roles validation
    allowed_roles = ['RSM', 'RBM', 'ZBM', 'NSM', 'Admin', 'System Administrator']
    if employee.designation not in allowed_roles:
        return Response({'success': False, 'error': 'You do not have permission to access this.'}, status=403)

    control, created = CampaignControl.objects.get_or_create(manager=employee)

    # POST REQUEST: Save Products or Toggle Status
    if request.method == 'POST':
        action = request.data.get('action')

        if action == 'toggle_campaign':
            control.is_weekly_focus_active = not control.is_weekly_focus_active
            control.save()
            status_text = "ON" if control.is_weekly_focus_active else "OFF"
            return Response({
                'success': True, 
                'is_campaign_active': control.is_weekly_focus_active,
                'message': f'Campaign is now {status_text}'
            })
        
        elif action == 'save_products':
            if not control.is_weekly_focus_active:
                return Response({'success': False, 'error': 'Campaign is OFF, products cannot be saved.'}, status=400)
            
            product_ids = request.data.get('product_ids', [])
            
            # Inactivate old selections
            FocusProductTracking.objects.filter(company=company, added_by=employee).update(is_active=False)
            
            # Save new selections
            for pid in product_ids:
                FocusProductTracking.objects.update_or_create(
                    company=company,
                    product_id=pid,
                    added_by=employee,
                    defaults={'is_active': True}
                )
            
            return Response({'success': True, 'message': 'Focus products saved successfully!'})
        
        return Response({'success': False, 'error': 'Invalid action parameter.'}, status=400)

    # GET REQUEST: Fetch Initial Screen Data
    all_products = Product.objects.filter(company=company).order_by('name')
    active_focus_ids = list(FocusProductTracking.objects.filter(
        company=company, added_by=employee, is_active=True
    ).values_list('product_id', flat=True))

    product_list = []
    active_products = []
    
    for p in all_products:
        is_active = p.id in active_focus_ids
        prod_data = {
            'id': p.id,
            'name': p.name,
            'pack_size': p.pack_size,
            'is_selected': is_active
        }
        product_list.append(prod_data)
        
        if is_active:
            active_products.append(prod_data)

    return Response({
        'success': True,
        'is_campaign_active': control.is_weekly_focus_active,
        'all_products': product_list,
        'active_products': active_products
    })


# ==============================================================================
# 5. API to View Weekly Sale HISTORY for a month (MR: apna, Manager: puri team)
# ==============================================================================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_weekly_sale_history(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'status': 'error', 'message': 'Employee profile missing'}, status=400)

    company = employee.company
    today = timezone.now().date()

    try:
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))
    except (TypeError, ValueError):
        return Response({'status': 'error', 'message': 'Invalid month/year.'}, status=400)

    is_manager_view = employee.designation != 'MR'

    # 🌟 MR: sirf khud ka data. Manager: puri team ka (get_dropdown_team se sub-team milta hai)
    if is_manager_view:
        team_employees = get_dropdown_team(employee, ordered=False)
        team_ids = list(team_employees.values_list('id', flat=True))
        if employee.id not in team_ids:
            team_ids.append(employee.id)
    else:
        team_ids = [employee.id]

    records = WeeklyStockistSaleMaster.objects.filter(
        company=company,
        employee_id__in=team_ids,
        week_ending_date__month=month,
        week_ending_date__year=year
    ).select_related('employee', 'stockist').order_by('employee__name', 'week_ending_date', 'stockist__name')

    history = []
    for r in records:
        history.append({
            'employee_id': r.employee_id,
            'employee_name': r.employee.name,
            'stockist_name': r.stockist.name,
            'week_ending_date': r.week_ending_date.strftime('%d %b %Y'),
            'total_sec_sale_value': float(r.total_sec_sale_value or 0),
            'total_closing_value': float(r.total_closing_value or 0),
        })

    return Response({
        'status': 'success',
        'is_manager_view': is_manager_view,
        'month': month,
        'year': year,
        'history': history,
    })
