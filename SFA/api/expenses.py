"""
SFA/api/expenses.py
===================
Flutter ke liye Expense REST API endpoints.
"""

import calendar
import json  # 🌟 FIX: json module import kiya
from datetime import datetime

from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from SFA.models import MonthlyExpenseReport, DailyExpense
from SFA.views.expenses import _fill_missing_dates


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expense_list(request):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    # 🚀 OPTIMIZATION: prefetch_related lagaya taaki N+1 loop na bane
    reports = MonthlyExpenseReport.objects.prefetch_related('daily_lines').filter(
        employee=employee
    ).order_by('-year', '-month')

    result = []
    for mr in reports:
        daily = mr.daily_lines.all()

        total_claimed = sum(
            float((l.ta_amount or 0) + (l.da_amount or 0) + (l.misc_amount or 0))
            for l in daily
        )

        total_approved = None
        if mr.status == 'Approved':
            total_approved = round(sum(
                float(
                    (l.approved_ta   if l.approved_ta   is not None else l.ta_amount) +
                    (l.approved_da   if l.approved_da   is not None else l.da_amount) +
                    (l.approved_misc if l.approved_misc is not None else l.misc_amount)
                )
                for l in daily
            ), 2)

        result.append({
            'id': mr.id,
            'month': mr.month,
            'year': mr.year,
            'month_name': f"{calendar.month_name[mr.month]} {mr.year}",
            'status': mr.status,
            'total_claimed': round(total_claimed, 2),
            'total_approved': total_approved,
            'manager_remark': mr.manager_remark or '',
        })

    return Response(result)

# ==============================================================================
# 📄 EXPENSE REPORT DETAIL
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expense_detail(request, report_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    mr = get_object_or_404(MonthlyExpenseReport, id=report_id, employee=employee)

    if mr.status in ('Draft', 'Rejected'):
        _fill_missing_dates(mr, employee)

    daily = mr.daily_lines.all().order_by('date')

    total_claimed = 0.0
    total_approved = 0.0
    lines = []

    for l in daily:
        claimed = float((l.ta_amount or 0) + (l.da_amount or 0) + (l.misc_amount or 0))
        approved = float(
            (l.approved_ta   if l.approved_ta   is not None else l.ta_amount) +
            (l.approved_da   if l.approved_da   is not None else l.da_amount) +
            (l.approved_misc if l.approved_misc is not None else l.misc_amount)
        )
        total_claimed += claimed
        total_approved += approved

        lines.append({
            'id': l.id,
            'date': str(l.date),
            'day_name': l.date.strftime('%A'),
            'territory_category': l.territory_category or 'HQ',
            'night_stay': bool(l.night_stay),
            'is_slab3': bool(l.is_slab3),
            'da_amount': float(l.da_amount or 0),
            'ta_amount': float(l.ta_amount or 0),
            'misc_amount': float(l.misc_amount or 0),
            'misc_bill_url': request.build_absolute_uri(l.misc_bill.url) if l.misc_bill else None,
            'remark': l.remark or '',            'distance_km': float(l.distance_km or 0),
            'approved_da': float(l.approved_da) if l.approved_da is not None else None,
            'approved_ta': float(l.approved_ta) if l.approved_ta is not None else None,
            'approved_misc': float(l.approved_misc) if l.approved_misc is not None else None,
            'day_total_claimed': round(claimed, 2),
            'day_total_approved': round(approved, 2),
        })

    return Response({
        'id': mr.id,
        'month': mr.month,
        'year': mr.year,
        'month_name': f"{calendar.month_name[mr.month]} {mr.year}",
        'status': mr.status,
        'manager_remark': mr.manager_remark or '',
        'total_claimed': round(total_claimed, 2),
        'total_approved': round(total_approved, 2) if mr.status == 'Approved' else None,
        'daily_lines': lines,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_expense_save(request, report_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    mr = get_object_or_404(MonthlyExpenseReport, id=report_id, employee=employee)

    if mr.status not in ('Draft', 'Rejected'):
        return Response(
            {'error': f"Report '{mr.status}' hai — sirf Draft ya Rejected report mein changes ho sakte hain."},
            status=400
        )

    lines_str = request.POST.get('lines') or request.data.get('lines')
    if not lines_str:
        return Response({'error': 'lines array required hai'}, status=400)

    try:
        lines_data = json.loads(lines_str) if isinstance(lines_str, str) else lines_str
    except Exception:
        return Response({'error': 'Invalid lines JSON format'}, status=400)

    try:
        # 🚀 OPTIMIZATION: Loop se pehle us mahine ke saare expenses memory me nikal liye (30 DB Calls saved)
        existing_expenses = {e.id: e for e in mr.daily_lines.all()}

        for item in lines_data:
            line_id = int(item.get('line_id'))
            misc = float(item.get('misc_amount') or 0)
            remark = item.get('remark', '')

            # RAM se dictionary fetch
            expense = existing_expenses.get(line_id)
            
            if expense:
                expense.misc_amount = misc
                expense.remark = remark
                
                bill_file = request.FILES.get(f'bill_{line_id}')
                if bill_file:
                    expense.misc_bill = bill_file
                
                expense.save() # FileField ki wajah se bulk_update use nahi kar sakte, par 30 SELECT queries bach gayi

        return Response({
            'message': '📝 Draft save ho gaya! Manager ko dikhane ke liye Submit karna mat bhoolo.'
        })

    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ==============================================================================
# 📤 SUBMIT FOR APPROVAL
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_expense_submit(request, report_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    mr = get_object_or_404(MonthlyExpenseReport, id=report_id, employee=employee)
    today = timezone.localdate()


    # Current month block
    if mr.year > today.year or (mr.year == today.year and mr.month >= today.month):
        return Response({
            'error': 'Current month ka expense abhi submit nahi ho sakta. Mahina khatam hone ke baad submit karein.'
        }, status=400)

    if mr.status not in ('Draft', 'Rejected'):
        return Response(
            {'error': f"Report already '{mr.status}' hai — dobara submit nahi ho sakti."},
            status=400
        )

    try:
        # 🌟 FIX: Multipart request handle karna (Save jaisa same logic)
        lines_str = request.POST.get('lines')
        if not lines_str:
            lines_str = request.data.get('lines')
            
        if lines_str:
            try:
                lines_data = json.loads(lines_str) if isinstance(lines_str, str) else lines_str
            except Exception:
                return Response({'error': 'Invalid lines JSON format'}, status=400)

            for item in lines_data:
                line_id = item.get('line_id')
                misc = float(item.get('misc_amount') or 0)
                remark = item.get('remark', '')

                expense = DailyExpense.objects.filter(id=line_id, monthly_report=mr).first()
                if expense:
                    expense.misc_amount = misc
                    expense.remark = remark
                    
                    # 🌟 NAYA: Submit karte time bhi Bill Photo Save karna
                    bill_file = request.FILES.get(f'bill_{line_id}')
                    if bill_file:
                        expense.misc_bill = bill_file
                        
                    expense.save()

        # Missing dates fill karo
        _fill_missing_dates(mr, employee)

        # Submit
        mr.status = 'Pending'
        mr.manager_remark = ''
        mr.is_modified = False
        mr.save()

        return Response({'message': '✅ Expense Report successfully submitted for approval!'})

    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ==============================================================================
# 🔄 REOPEN (REJECTED → DRAFT)
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_expense_reopen(request, report_id):
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    updated = MonthlyExpenseReport.objects.filter(
        id=report_id, employee=employee, status='Rejected'
    ).update(status='Draft')

    if updated:
        return Response({'message': '📝 Report wapas Draft mein aa gayi. Ab changes kar sakte hain.'})
    else:
        return Response(
            {'error': 'Report nahi mili ya already Draft/Pending/Approved hai.'},
            status=400
        )