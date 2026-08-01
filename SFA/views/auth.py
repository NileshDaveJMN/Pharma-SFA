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
]


def login_view(request):
    """Standard Django session-based login — web browser ke liye."""
    if request.user.is_authenticated:
        if not hasattr(request.user, 'employee'):
            return redirect('/admin/')
        return redirect('mr_dashboard')

    if request.method == 'POST':
        comp_code = request.POST.get('company_code', '').strip().upper()
        
        # 🌟 FIX: Mobile number ko teeno possible names se check karo
        phone = (
            request.POST.get('mobile_number') or 
            request.POST.get('username') or 
            request.POST.get('phone') or ''
        ).strip()
        
        password = request.POST.get('password', '')

        # 1. Company Code + Phone combine karke username banao
        if comp_code and phone:
            django_username = f"{comp_code}_{phone}"
        else:
            django_username = phone  # Fallback for direct username / admin

        user = authenticate(username=django_username, password=password)

        # 2. Fallback: Agar upar se authenticate na hua ho (case difference etc.)
        if not user and comp_code and phone:
            user = authenticate(username=f"{comp_code.lower()}_{phone}", password=password)

        if user:
            login(request, user)
            if not hasattr(user, 'employee'):
                return redirect('/admin/')
            return redirect('mr_dashboard')
            
        return render(request, 'login.html', {'error': 'Invalid Company Code, Mobile No. or Password'})

    return render(request, 'login.html')

def logout_view(request):
    """Session logout — web browser ke liye."""
    logout(request)
    return redirect('login')
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages

def custom_logout_view(request):
    logout(request)  # 🧹 Ye line actual session/cookies destroy karti hai
    messages.success(request, "Aap successfully logout ho gaye hain.")
    return redirect('/login')  # Logout hone ke baad login page par bhejein
