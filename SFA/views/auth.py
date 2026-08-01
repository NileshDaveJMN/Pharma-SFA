"""
SFA/views/auth.py
=================
Web-facing auth views: login, logout.

Saare team/territory helpers ab yahan NAHI hain —
wo SFA/services/team.py mein hain.

Doosri views files import karein:
    from SFA.services.team import get_full_team_employees, ...

🌟 BACKWARD COMPATIBILITY: Jo bhi file pehle auth.py se import karti thi
   (core.py, reports.py, sales.py etc.) wo abhi bhi kaam karegi bina
   kisi change ke — kyunki hum yahan re-export kar rahe hain.
"""

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages

# 🌟 Re-export saare helpers from services layer
# Purane imports (from .auth import get_full_team_employees) todenge nahi
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
# 🔐 LOGIN — Web browser ke liye (session-based)
# ==============================================================================

def login_view(request):
    if request.method == 'POST':
        comp_code = request.POST.get('company_code', '').strip()

        # Dabbe se jo bhi input mila (mobile number ya sirf naam)
        entered_username = (
            request.POST.get('mobile_number') or
            request.POST.get('username') or
            request.POST.get('phone') or ''
        ).strip()

        password = request.POST.get('password', '')

        user = None

        # 🎯 LOGIC 1: Purane users ke liye — exact username match (case-insensitive lookup)
        if entered_username:
            candidate = User.objects.filter(username__iexact=entered_username).first()
            if candidate:
                user = authenticate(username=candidate.username, password=password)

        # 🎯 LOGIC 2: Naye users ke liye — "COMPCODE_mobile" pattern (case-insensitive lookup)
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
    """Session logout — web browser ke liye."""
    logout(request)
    return redirect('login')


def custom_logout_view(request):
    logout(request)  # 🧹 Ye line actual session/cookies destroy karti hai
    messages.success(request, "You have been logged out successfully.")
    return redirect('/login')  # Logout hone ke baad login page par bhejein