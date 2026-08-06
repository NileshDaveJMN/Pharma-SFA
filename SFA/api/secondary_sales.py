import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from SFA.models import Stockist, FocusProductTracking, WeeklyStockistSaleMaster, WeeklyStockistSaleDetail

# 1. API to get list of Stockists and their submission status
@csrf_exempt
def get_pending_stockists(request):
    try:
        employee = request.user.employee
        company = employee.company
        
        # Flutter app will pass the Saturday date it is asking for
        # e.g., /api/secondary-sales/stockists/?date=2026-08-08
        target_date = request.GET.get('date')
        if not target_date:
            return JsonResponse({'status': 'error', 'message': 'Date parameter is required.'})
            
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
            
        return JsonResponse({'status': 'success', 'data': data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# 2. API to get the list of active Focus Products
@csrf_exempt
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
            
        return JsonResponse({'status': 'success', 'data': data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# 3. API to Submit the Weekly Sales Data
@csrf_exempt
def submit_weekly_sales(request):
    if request.method == 'POST':
        try:
            employee = request.user.employee
            company = employee.company
            data = json.loads(request.body)
            
            stockist_id = data.get('stockist_id')
            week_ending_date = data.get('week_ending_date') # Flutter will send this
            total_sec = data.get('total_sec_sale_value', 0)
            total_close = data.get('total_closing_value', 0)
            items = data.get('items', []) # [{'product_id': 1, 'sec_sale_qty': 10, 'closing_qty': 50}]
            
            if not week_ending_date:
                return JsonResponse({'status': 'error', 'message': 'week_ending_date is required.'})
            
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
                    
            return JsonResponse({'status': 'success', 'message': 'Weekly Sales saved successfully!'})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Only POST method allowed'})
