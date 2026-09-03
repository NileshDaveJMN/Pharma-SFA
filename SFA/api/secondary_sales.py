import json
from datetime import date, timedelta
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction

from SFA.models import (
    Stockist, 
    FocusProductTracking, 
    WeeklyStockistSaleMaster, 
    WeeklyStockistSaleDetail,
    Product,
    CampaignControl
)
from SFA.services.team import get_full_team_employees


def _get_week_window():
    today = date.today()
    weekday = today.weekday()

    if weekday == 5:
        last_saturday = today
    elif weekday == 6:
        last_saturday = today - timedelta(days=1)
    elif weekday == 0:
        last_saturday = today - timedelta(days=2)
    else:
        days_since_saturday = (weekday + 2) % 7
        last_saturday = today - timedelta(days=days_since_saturday)

    is_locked = weekday not in [0, 5, 6] 
    return last_saturday, is_locked


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pending_stockists(request):
    try:
        employee = request.user.employee
        company = employee.company

        auto_saturday, is_locked = _get_week_window()
        target_date = request.query_params.get('date') or str(auto_saturday)
            
        stockists = Stockist.objects.filter(territory=employee.headquarter, company=company)
        
        # 🚀 OPTIMIZATION 1: set() mein convert kiya taaki loop me N+1 queries fire na hon
        submitted_ids = set(WeeklyStockistSaleMaster.objects.filter(
            employee=employee, week_ending_date=target_date
        ).values_list('stockist_id', flat=True))
        
        data = [
            {
                'id': s.id,
                'name': s.name,
                'status': 'Submitted' if s.id in submitted_ids else 'Pending'
            } for s in stockists
        ]
            
        return Response({
            'status': 'success',
            'data': data,
            'week_ending_date': target_date,
            'is_locked': is_locked,
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_focus_products(request):
    try:
        employee = request.user.employee
        company = employee.company
        
        # 🚀 OPTIMIZATION 2: select_related lagaya taaki Product query 1 baar me aaye
        active_focus = FocusProductTracking.objects.filter(company=company, is_active=True).select_related('product')
        data = [
            {
                'product_id': f.product.id,
                'name': f.product.name,
                'pack_size': f.product.pack_size,
            } for f in active_focus
        ]
            
        return Response({'status': 'success', 'data': data})
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_weekly_sales(request):
    try:
        employee = request.user.employee
        company = employee.company
        data = request.data
        
        stockist_id = data.get('stockist_id')
        week_ending_date = data.get('week_ending_date')
        total_sec = data.get('total_sec_sale_value', 0)
        total_close = data.get('total_closing_value', 0)
        items = data.get('items', [])
        
        if not week_ending_date:
            return Response({'status': 'error', 'message': 'week_ending_date is required.'}, status=400)

        _, is_locked = _get_week_window()
        if is_locked:
            return Response({
                'status': 'error',
                'message': 'Entry locked! Data submission is only permitted on Saturdays, Sundays, and Mondays.'
            }, status=403)
        
        with transaction.atomic():
            master, _ = WeeklyStockistSaleMaster.objects.update_or_create(
                company=company,
                stockist_id=stockist_id,
                week_ending_date=week_ending_date,
                defaults={
                    'employee': employee,
                    'total_sec_sale_value': total_sec,
                    'total_closing_value': total_close
                }
            )
            
            WeeklyStockistSaleDetail.objects.filter(master=master).delete()
            
            # 🚀 OPTIMIZATION 3: Loop ke andar Create ki jagah Bulk Create (N queries reduced to 1)
            details_to_create = []
            for item in items:
                sec_qty = int(item.get('sec_sale_qty', 0))
                closing_qty = int(item.get('closing_qty', 0))
                
                if sec_qty > 0 or closing_qty > 0:
                    details_to_create.append(WeeklyStockistSaleDetail(
                        master=master,
                        product_id=item['product_id'],
                        sec_sale_qty=sec_qty,
                        closing_qty=closing_qty
                    ))
            
            if details_to_create:
                WeeklyStockistSaleDetail.objects.bulk_create(details_to_create)
                
        return Response({'status': 'success', 'message': 'Weekly Sales saved successfully!'})
        
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_weekly_sale_detail(request):
    try:
        employee = request.user.employee
        stockist_id = request.query_params.get('stockist_id')
        week_ending_date = request.query_params.get('date')

        if not stockist_id or not week_ending_date:
            return Response({'status': 'error', 'message': 'stockist_id and date are required.'}, status=400)

        try:
            master = WeeklyStockistSaleMaster.objects.get(
                employee=employee, stockist_id=stockist_id, week_ending_date=week_ending_date
            )
        except WeeklyStockistSaleMaster.DoesNotExist:
            return Response({'status': 'success', 'found': False})

        details = WeeklyStockistSaleDetail.objects.filter(master=master)
        details_data = {
            str(d.product_id): {'sec_sale_qty': d.sec_sale_qty, 'closing_qty': d.closing_qty}
            for d in details
        }

        return Response({
            'status': 'success',
            'found': True,
            'total_sec_sale_value': master.total_sec_sale_value,
            'total_closing_value': master.total_closing_value,
            'details': details_data,
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def weekly_sale_history(request):
    try:
        employee = request.user.employee
        today = date.today()
        month = int(request.query_params.get('month') or today.month)
        year = int(request.query_params.get('year') or today.year)

        is_manager_view = employee.designation not in ['MR']

        if is_manager_view:
            team_employees = get_full_team_employees(employee)
            qs = WeeklyStockistSaleMaster.objects.filter(
                employee__in=team_employees,
                week_ending_date__month=month,
                week_ending_date__year=year,
            )
        else:
            qs = WeeklyStockistSaleMaster.objects.filter(
                employee=employee,
                week_ending_date__month=month,
                week_ending_date__year=year,
            )

        qs = qs.select_related('employee', 'stockist').prefetch_related('details__product').order_by('-week_ending_date', 'employee__name')

        history = []
        for m in qs:
            products = [{
                'product_id': d.product_id,
                'name': d.product.name,
                'pack_size': d.product.pack_size,
                'sec_sale_qty': d.sec_sale_qty,
                'closing_qty': d.closing_qty,
            } for d in m.details.all()]

            history.append({
                'employee_name': m.employee.name,
                'stockist_name': m.stockist.name,
                'week_ending_date': str(m.week_ending_date),
                'total_sec_sale_value': float(m.total_sec_sale_value),
                'total_closing_value': float(m.total_closing_value),
                'products': products,
            })

        return Response({
            'status': 'success',
            'is_manager_view': is_manager_view,
            'history': history,
        })
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_rsm_manage_focus_products(request):
    employee = request.user.employee
    company = employee.company

    allowed_roles = ['RSM', 'RBM', 'ZBM', 'NSM', 'Admin', 'System Administrator']
    if employee.designation not in allowed_roles:
        return Response({'success': False, 'error': 'You do not have permission to access this.'}, status=403)

    control, _ = CampaignControl.objects.get_or_create(manager=employee)

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
            
            with transaction.atomic():
                FocusProductTracking.objects.filter(
                    company=company, added_by=employee
                ).update(is_active=False)
                
                new_trackings = [
                    FocusProductTracking(
                        company=company,
                        product_id=pid,
                        added_by=employee,
                        is_active=True
                    )
                    for pid in product_ids
                ]
                if new_trackings:
                    FocusProductTracking.objects.bulk_create(
                        new_trackings,
                        update_conflicts=True,
                        unique_fields=['company', 'product', 'added_by'],
                        update_fields=['is_active']
                    )
            
            return Response({'success': True, 'message': 'Focus products saved successfully!'})
        
        return Response({'success': False, 'error': 'Invalid action parameter.'}, status=400)

    all_products = Product.objects.filter(company=company).order_by('name')
    active_focus_ids = set(FocusProductTracking.objects.filter(
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
