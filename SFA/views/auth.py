"""
SFA/views/auth.py
=================
Web-facing auth views: login, logout.

All team/territory helpers are NO LONGER located here —
they have been moved to SFA/services/team.py.

Please import them from the new services file:
    from SFA.services.team import get_full_team_employees, ...

🌟 BACKWARD COMPATIBILITY: Any file that previously imported from auth.py
   (e.g., core.py, reports.py, sales.py, etc.) will continue to function 
   without any changes because we are re-exporting the modules here.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages

# 🌟 Re-export all helpers from the services layer 
# to ensure existing legacy imports do not break
from SFA.services.team import (
    get_full_team_employees,
    get_team_territory_ids,
    get_team_route_ids,
    get_team_hq_territory_ids,
    get_team_requested_routes,
    get_team_tree,
    get_dropdown_team,
    get_data_scope,
    get_own_territories_and_routes,
)

__all__ = [
    'get_full_team_employees',
    'get_team_territory_ids',
    'get_team_route_ids',
    'get_team_hq_territory_ids',
    'get_team_requested_routes',
    'get_team_tree',
    'get_dropdown_team',
    'get_data_scope',
    'get_own_territories_and_routes',
    'login_view',
    'logout_view',
    'custom_logout_view',
]


# ==============================================================================
# 🔐 LOGIN — For Web Browser (Session-based)
# ==============================================================================

def login_view(request):
    if request.method == 'POST':
        comp_code = request.POST.get('company_code', '').strip()

        # Retrieve the input provided in the form field (mobile number or username)
        entered_username = (
            request.POST.get('mobile_number') or
            request.POST.get('username') or
            request.POST.get('phone') or ''
        ).strip()

        password = request.POST.get('password', '')

        user = None

        # 🎯 LOGIC 1: For legacy users — exact username match (case-insensitive lookup)
        if entered_username:
            candidate = User.objects.filter(username__iexact=entered_username).first()
            if candidate:
                user = authenticate(username=candidate.username, password=password)

        # 🎯 LOGIC 2: For new users — "COMPCODE_mobile" pattern (case-insensitive lookup)
        if not user and comp_code and entered_username:
            combined = f"{comp_code}_{entered_username}"
            candidate = User.objects.filter(username__iexact=combined).first()
            if candidate:
                user = authenticate(username=candidate.username, password=password)

        if user:
            login(request, user)
            if not hasattr(user, 'employee'):
                return redirect('/admin/')
            return redirect('mr_dashboard')

        return render(request, 'login.html', {'error': 'Invalid Company Code, Username or Password'})

    return render(request, 'login.html')


# ==============================================================================
# 🚪 LOGOUT — Session logout
# ==============================================================================

def logout_view(request):
    """Session logout for the web browser."""
    logout(request)
    return redirect('login')


def custom_logout_view(request):
    logout(request)  # 🧹 This line clears the actual session/cookies
    messages.success(request, "You have been logged out successfully.")
    return redirect('/login')  # Redirect to the login page after logout
