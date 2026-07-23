from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from SFA.models import Employee


def employee_required(view_func):
    """
    Replaces the pattern repeated across views/core.py, views/masters.py,
    views/reports.py and views/sales.py:

        @login_required(login_url='/login/')
        def some_view(request):
            try:
                employee = request.user.employee
            except AttributeError:
                ...

    Usage:

        @employee_required
        def some_view(request, employee):
            ...   # employee is already fetched, no boilerplate needed

    URL params still work normally since Django passes them as keyword
    arguments:

        @employee_required
        def doctor_visit_view(request, employee, doc_id):
            ...

    Note: in the original mr_dashboard_view, a missing employee profile
    rendered 'dashboard.html' with an error instead of redirecting. This
    decorator standardises that edge case to a redirect + error message,
    matching how the rest of the project already handles a missing profile.
    """
    @login_required(login_url='/login/')
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            employee = request.user.employee
        except (AttributeError, Employee.DoesNotExist):
            messages.error(request, "Employee profile missing. Please contact Admin.")
            return redirect('user_login')
        return view_func(request, employee, *args, **kwargs)
    return wrapper
