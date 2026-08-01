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


    if request.method == 'POST':
        comp_code = request.POST.get('company_code', '').strip().upper()
        
        # Dabbe se jo bhi input mila (mobile number ya sirf naam)
        entered_username = (
            request.POST.get('mobile_number') or 
            request.POST.get('username') or 
            request.POST.get('phone') or ''
        ).strip()
        
        password = request.POST.get('password', '')

        # 🎯 LOGIC 1: Pehle purane users ke liye EXACT match try karo (e.g., 'bhavesh' ya 'admin')
        user = authenticate(username=entered_username, password=password)

        # 🎯 LOGIC 2: Agar exact match fail ho gaya, toh naye users ke liye combine karke check karo
        if not user and comp_code and entered_username:
            user = authenticate(username=f"{comp_code}_{entered_username}", password=password)

        # 🎯 LOGIC 3: Fallback (Agar case ka koi issue ho)
        if not user and comp_code and entered_username:
            user = authenticate(username=f"{comp_code.lower()}_{entered_username}", password=password)

        if user:
            login(request, user)
            if not hasattr(user, 'employee'):
                return redirect('/admin/')
            return redirect('mr_dashboard')
            
        return render(request, 'login.html', {'error': 'Invalid Company Code, Username or Password'})

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
