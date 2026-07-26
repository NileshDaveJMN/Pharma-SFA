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
from datetime import datetime # 🌟 NAYA: Date parse karne ke liye

from SFA.services.team import get_team_tree, get_full_team_employees
from SFA.models import SystemSetting, DeviceToken, Employee

# ==============================================================================
# 🔐 LOGIN — Token return karta hai
# ==============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
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

    try:
        emp = user.employee
    except AttributeError:
        return Response(
            {'error': 'Employee profile missing. Admin se contact karein.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if emp.company.code != company_code:
        return Response(
            {'error': 'Invalid Company Code ya phir ye user is company ka nahi hai.'},
            status=status.HTTP_403_FORBIDDEN
        )

    token, _ = Token.objects.get_or_create(user=user)
    django_login(request._request, user)

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
        emp_id = request.query_params.get('employee_id')
        
        if emp_id:
            try:
                target_emp = Employee.objects.get(id=emp_id, company=emp.company)
                team_members = get_full_team_employees(emp)
                managers = emp.get_my_managers()
                allowed_ids = set(team_members.values_list('id', flat=True)) | set([m.id for m in managers])
                
                if target_emp.id not in allowed_ids and target_emp.id != emp.id:
                    return Response({'error': 'Access Denied: You can only view your team members.'}, status=403)
                    
                emp = target_emp
            except Employee.DoesNotExist:
                return Response({'error': 'Employee not found'}, status=404)

        data = _employee_dict(emp, include_manager=True)
        return Response(data, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        action = request.data.get('action')

        if action == 'update_profile':
            emp.phone = request.data.get('phone', emp.phone)
            emp.address = request.data.get('address', emp.address)
            
            # 🌟 NAYA: Personal Info Update
            emp.dob = request.data.get('dob') or None
            emp.anniversary = request.data.get('anniversary') or None
            emp.blood_group = request.data.get('blood_group') or None
            emp.emergency_contact = request.data.get('emergency_contact') or None
            emp.permanent_address = request.data.get('permanent_address') or None
            
            # 🌟 NAYA: Family Info Update
            emp.father_name = request.data.get('father_name') or None
            emp.father_dob = request.data.get('father_dob') or None
            emp.father_mobile = request.data.get('father_mobile') or None
            emp.father_occupation = request.data.get('father_occupation') or None
            
            emp.mother_name = request.data.get('mother_name') or None
            emp.mother_dob = request.data.get('mother_dob') or None
            emp.mother_mobile = request.data.get('mother_mobile') or None
            emp.mother_occupation = request.data.get('mother_occupation') or None
            
            emp.spouse_name = request.data.get('spouse_name') or None
            emp.spouse_dob = request.data.get('spouse_dob') or None
            emp.spouse_mobile = request.data.get('spouse_mobile') or None
            emp.spouse_occupation = request.data.get('spouse_occupation') or None
            
            emp.child1_name = request.data.get('child1_name') or None
            emp.child1_dob = request.data.get('child1_dob') or None
            emp.child2_name = request.data.get('child2_name') or None
            emp.child2_dob = request.data.get('child2_dob') or None
            
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
# 🌳 ORGANOGRAM (Hierarchy Tree)
# ==============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_organogram(request):
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=400)

    nodes = []
    
    managers = emp.get_my_managers(include_inactive=False)
    managers.reverse()
    for m in managers:
        nodes.append({
            'id': m.id,
            'name': m.name,
            'role': m.designation,
            'hq': m.headquarter.name if m.headquarter else 'N/A',
            'is_me': False,
            'is_vacant': False,
            'depth': 0
        })
        
    nodes.append({
        'id': emp.id,
        'name': f"{emp.name} (You)",
        'role': emp.designation,
        'hq': emp.headquarter.name if emp.headquarter else 'N/A',
        'is_me': True,
        'is_vacant': False,
        'depth': 0
    })
    
    def get_subs(parent, depth):
        direct_reports = Employee.objects.filter(manager=parent).exclude(id=parent.id).order_by('name')
        for sub in direct_reports:
            if not sub.is_active and not sub.is_placeholder:
                continue
                
            is_vacant = sub.is_placeholder
            nodes.append({
                'id': sub.id,
                'name': 'Vacant Position' if is_vacant else sub.name,
                'role': sub.designation,
                'hq': sub.headquarter.name if sub.headquarter else 'N/A',
                'is_me': False,
                'is_vacant': is_vacant,
                'depth': depth
            })
            get_subs(sub, depth + 1)
            
    get_subs(emp, 1)
        
    return Response(nodes, status=200)

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
        'joining_date': str(emp.joining_date) if emp.joining_date else 'N/A', # 🌟 NAYA

        
        # 🌟 NAYA: Personal Info
        'dob': str(emp.dob) if emp.dob else None,
        'anniversary': str(emp.anniversary) if emp.anniversary else None,
        'blood_group': emp.blood_group or '',
        'emergency_contact': emp.emergency_contact or '',
        'permanent_address': emp.permanent_address or '',
        
        # 🌟 NAYA: Family Info
        'father_name': emp.father_name or '',
        'father_dob': str(emp.father_dob) if emp.father_dob else None,
        'father_mobile': emp.father_mobile or '',
        'father_occupation': emp.father_occupation or '',
        
        'mother_name': emp.mother_name or '',
        'mother_dob': str(emp.mother_dob) if emp.mother_dob else None,
        'mother_mobile': emp.mother_mobile or '',
        'mother_occupation': emp.mother_occupation or '',
        
        'spouse_name': emp.spouse_name or '',
        'spouse_dob': str(emp.spouse_dob) if emp.spouse_dob else None,
        'spouse_mobile': emp.spouse_mobile or '',
        'spouse_occupation': emp.spouse_occupation or '',
        
        'child1_name': emp.child1_name or '',
        'child1_dob': str(emp.child1_dob) if emp.child1_dob else None,
        'child2_name': emp.child2_name or '',
        'child2_dob': str(emp.child2_dob) if emp.child2_dob else None,
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