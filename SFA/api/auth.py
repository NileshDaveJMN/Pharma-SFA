"""
SFA/api/auth.py
===============
Flutter ke liye REST API endpoints — Authentication & Profile.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate, login as django_login

from SFA.services.team import get_team_tree, get_full_team_employees
from SFA.models import SystemSetting, DeviceToken

# ==============================================================================
# 🔐 LOGIN — Token return karta hai
# ==============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    # 🌟 MULTI-COMPANY: Company Code bhi lena hai
    company_code = request.data.get('company_code', '').strip()
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not company_code or not username or not password:
        return Response(
            {'error': 'Company Code, Username aur Password teeno required hain'},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = authenticate(username=username, password=password)

    if user is None:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.is_active:
        return Response(
            {'error': 'Account inactive hai. Admin se contact karein.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Employee profile check
    try:
        emp = user.employee
    except AttributeError:
        return Response(
            {'error': 'Employee profile missing. Admin se contact karein.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 🌟 MULTI-COMPANY CHECK: User usi company ka hai ya nahi?
    if emp.company.code != company_code:
        return Response(
            {'error': 'Invalid Company Code ya phir ye user is company ka nahi hai.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Token create ya fetch (idempotent)
    token, _ = Token.objects.get_or_create(user=user)

    # Django session bhi create karo — WebView ke liye
    django_login(request._request, user)

    # Offline Mode Setting fetch karo
    setting = SystemSetting.objects.filter(company=emp.company).first()
    is_offline_mode = setting.enable_offline_mode if setting else True

    return Response({
        'token': token.key,
        'employee': _employee_dict(emp),
        'enable_offline_mode': is_offline_mode,
    }, status=status.HTTP_200_OK)


# ==============================================================================
# 🚪 LOGOUT — Token delete karta hai
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    try:
        request.user.auth_token.delete()
    except Exception:
        pass
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


# ==============================================================================
# 👤 PROFILE & TEAM
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_team_tree(request):
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=status.HTTP_400_BAD_REQUEST)

    tree = get_team_tree(emp)
    return Response(_serialize_tree(tree), status=status.HTTP_200_OK)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def api_profile(request):
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        # 🌟 NAYA: Agar Manager kisi team member ka profile dekhna chahta hai
        emp_id = request.query_params.get('employee_id')
        
        if emp_id:
            try:
                target_emp = Employee.objects.get(id=emp_id, company=emp.company)
                # 🛡️ Security Check: Kya ye employee uski team ya hierarchy mein hai?
                team_members = get_full_team_employees(emp)
                managers = emp.get_my_managers()
                allowed_ids = set(team_members.values_list('id', flat=True)) | set([m.id for m in managers])
                
                if target_emp.id not in allowed_ids and target_emp.id != emp.id:
                    return Response({'error': 'Access Denied: You can only view your team members.'}, status=403)
                    
                emp = target_emp # Agar sab sahi hai, toh profile target employee ki dikhao
            except Employee.DoesNotExist:
                return Response({'error': 'Employee not found'}, status=404)

        data = _employee_dict(emp, include_manager=True)
        return Response(data, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        action = request.data.get('action')

        if action == 'update_profile':
            emp.phone = request.data.get('phone', emp.phone)
            emp.address = request.data.get('address', emp.address)
            
            if 'photo' in request.FILES:
                emp.photo = request.FILES['photo']
                
            emp.save()
            return Response({'message': 'Profile updated successfully!', 'employee': _employee_dict(emp, True)})

        elif action == 'change_password':
            old_pwd = request.data.get('old_password')
            new_pwd = request.data.get('new_password')
            
            if not request.user.check_password(old_pwd):
                return Response({'error': 'Old password is wrong'}, status=400)
                
            request.user.set_password(new_pwd)
            request.user.save()
            return Response({'message': 'Password updated successfully!!'})

        return Response({'error': 'Invalid action'}, status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_save_token(request):
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)
        
    token = request.data.get('token')
    if not token:
        return Response({'error': 'Token required'}, status=400)
        
    DeviceToken.objects.update_or_create(employee=emp, defaults={'token': token})
    return Response({'success': True, 'message': 'Token saved successfully!'})


# ==============================================================================
# 🔧 PRIVATE HELPERS
# ==============================================================================

def _employee_dict(emp, include_manager=False):
    data = {
        'id': emp.id,
        'name': emp.name,
        'designation': emp.designation,
        'phone': emp.phone or '',
        'address': emp.address or '',
        'hq': emp.headquarter.name if emp.headquarter else None,
        'hq_id': emp.headquarter_id,
        'photo_url': emp.photo.url if emp.photo else None,
    }
    if include_manager and emp.manager:
        data['manager'] = {
            'id': emp.manager.id,
            'name': emp.manager.name,
            'designation': emp.manager.designation,
            'phone': emp.manager.phone or '',
        }
    else:
        data['manager'] = None
    return data

def _serialize_tree(nodes):
    result = []
    for node in nodes:
        emp = node['emp']
        result.append({
            'id': emp.id,
            'name': emp.name,
            'designation': emp.designation,
            'phone': emp.phone or '',
            'hq': emp.headquarter.name if emp.headquarter else None,
            'children': _serialize_tree(node['children']),
        })
    return result