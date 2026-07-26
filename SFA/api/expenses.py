"""
SFA/api/expenses.py
===================
Flutter ke liye Expense REST API endpoints.

Endpoints:
    GET    /api/expenses/                    → Meri saari expense reports list
    GET    /api/expenses/<id>/               → Ek report ki daily lines detail
    POST   /api/expenses/<id>/save/          → Misc + remark save (Draft)
    POST   /api/expenses/<id>/submit/        → Submit for approval
    POST   /api/expenses/<id>/reopen/        → Rejected → Draft wapas
"""

import calendar
from datetime import datetime

from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from SFA.models import MonthlyExpenseReport, DailyExpense
from SFA.views.expenses import _fill_missing_dates


# ==============================================================================
# 📋 EXPENSE REPORTS LIST
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expense_list(request):
    """
    Employee ki saari monthly expense reports.

    Response:
    [
        {
            "id": 12,
            "month": 5, "year": 2026,
            "month_name": "May 2026",
            "status": "Draft",          // Draft | Pending | Approved | Rejected
            "total_claimed": 4500.0,
            "total_approved": null,     // sirf Approved reports mein value hogi
            "manager_remark": ""
        }
    ]
    """
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    reports = MonthlyExpenseReport.objects.filter(
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
    """
    Ek monthly report ki puri daily lines.

    Response:
    {
        "id": 12,
        "month": 5, "year": 2026,
        "month_name": "May 2026",
        "status": "Draft",
        "manager_remark": "",
        "total_claimed": 4500.0,
        "total_approved": null,
        "daily_lines": [
            {
                "id": 101,
                "date": "2026-05-01",
                "day_name": "Friday",
                "territory_category": "HQ",   // HQ | EX_HQ | OUTSTATION
                "night_stay": false,
                "is_slab3": false,             // true = Admin manually approve karega
                "da_amount": 200.0,
                "ta_amount": 150.0,
                "misc_amount": 0.0,
                "remark": "",
                "distance_km": 25.0,
                "approved_da": null,           // null = claimed hi approved maano
                "approved_ta": null,
                "approved_misc": null,
                "day_total_claimed": 350.0,
                "day_total_approved": 350.0
            }
        ]
    }
    """
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    mr = get_object_or_404(MonthlyExpenseReport, id=report_id, employee=employee)

    # Smart recovery — missing dates fill karo
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
            'remark': l.remark or '',
            'distance_km': float(l.distance_km or 0),
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


# ==============================================================================
# 💾 SAVE MISC (DRAFT)
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_expense_save(request, report_id):
    """
    Misc amount, remarks aur Bill Photo save karo — Draft mein rehta hai, submit nahi hota.
    (Supports Multipart/form-data for file uploads)
    """
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

    # 🌟 FIX: Multipart request handle karna
    lines_str = request.POST.get('lines')
    if not lines_str:
        lines_str = request.data.get('lines') # Fallback for standard JSON
        
    if not lines_str:
        return Response({'error': 'lines array required hai'}, status=400)

    try:
        lines_data = json.loads(lines_str) if isinstance(lines_str, str) else lines_str
    except Exception:
        return Response({'error': 'Invalid lines JSON format'}, status=400)

    try:
        for item in lines_data:
            line_id = item.get('line_id')
            misc = float(item.get('misc_amount') or 0)
            remark = item.get('remark', '')

            expense = DailyExpense.objects.filter(id=line_id, monthly_report=mr).first()
            if expense:
                expense.misc_amount = misc
                expense.remark = remark
                
                # 🌟 NAYA: Bill Photo Save karna
                bill_file = request.FILES.get(f'bill_{line_id}')
                if bill_file:
                    expense.misc_bill = bill_file
                
                expense.save()

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
    """
    Expense report submit karo — Draft/Rejected → Pending.

    POST body (JSON):
    {
        "lines": [           // optional — save + submit ek saath
            {
                "line_id": 101,
                "misc_amount": 150.0,
                "remark": "Auto rickshaw"
            }
        ]
    }

    Success (200):
    { "message": "Expense Report successfully submitted!" }

    Error (400):
    { "error": "Current month ka expense abhi submit nahi ho sakta." }
    """
    try:
        employee = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    mr = get_object_or_404(MonthlyExpenseReport, id=report_id, employee=employee)
    today = timezone.now().date()

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
        # Pehle misc/remark save karo agar diye hain
        lines_data = request.data.get('lines', [])
        for item in lines_data:
            line_id = item.get('line_id')
            misc = float(item.get('misc_amount') or 0)
            remark = item.get('remark', '')
            DailyExpense.objects.filter(
                id=line_id, monthly_report=mr
            ).update(misc_amount=misc, remark=remark)

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
    """
    Rejected report ko wapas Draft mein daalo taaki changes ho sakein.

    Success (200):
    { "message": "Report wapas Draft mein aa gayi. Ab changes kar sakte hain." }
    """
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
