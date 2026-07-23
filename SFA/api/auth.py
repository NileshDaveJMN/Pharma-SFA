"""
SFA/api/auth.py
===============
Flutter ke liye REST API endpoints — Authentication & Profile.

Endpoints:
    POST   /api/auth/login/       → Token milega
    POST   /api/auth/logout/      → Token delete hoga
    GET    /api/auth/profile/     → Logged-in employee ki detail
    GET    /api/auth/team/        → Puri nested team tree

Flutter mein usage:
    final res = await http.post(
        Uri.parse('$BASE_URL/api/auth/login/'),
        body: {'username': 'MR001', 'password': 'xxxx'},
    );
    final token = jsonDecode(res.body)['token'];
    // Aage har request mein: headers: {'Authorization': 'Token $token'}

Install (agar nahi kiya):
    pip install djangorestframework
    pip install django-cors-headers

settings.py mein add karo:
    INSTALLED_APPS = [..., 'rest_framework', 'rest_framework.authtoken', 'corsheaders']
    MIDDLEWARE = ['corsheaders.middleware.CorsMiddleware', ...]
    CORS_ALLOWED_ORIGINS = ['http://localhost:*']   # Flutter dev ke liye
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.TokenAuthentication'],
        'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    }
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from SFA.models import DeviceToken
from django.contrib.auth import authenticate, login as django_login
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token

from SFA.services.team import get_team_tree
from SFA.models import SystemSetting # 🌟 NAYA IMPORT: SystemSetting ke liye


# ==============================================================================
# 🔐 LOGIN — Token return karta hai
# ==============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """
    Flutter se login.

    Request body (form-data ya JSON dono chalega):
        username: "MR001"
        password: "secret"

    Success response (200):
        {
            "token": "abc123...",
            "employee": {
                "id": 5,
                "name": "Rajesh Kumar",
                "designation": "MR",
                "phone": "9876543210",
                "hq": "Andheri",
                "hq_id": 3,
                "photo_url": "/media/photos/raj.jpg"  // null if no photo
            },
            "enable_offline_mode": true // 🌟 NAYA: Offline mode setting
        }

    Error response (401):
        { "error": "Invalid credentials" }

    Error response (403):
        { "error": "Account inactive" }

    Error response (400):
        { "error": "Employee profile missing" }
    """
    username = request.data.get('username', '').strip()
    password = request.data.get('password', '').strip()

    if not username or not password:
        return Response(
            {'error': 'Username aur password dono required hain'},
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

    # Token create ya fetch (idempotent)
    token, _ = Token.objects.get_or_create(user=user)

    # Django session bhi create karo — WebView ke liye
    django_login(request._request, user)

    # 🌟 NAYA: Offline Mode Setting fetch karo
    setting = SystemSetting.objects.filter(company=emp.company).first()
    is_offline_mode = setting.enable_offline_mode if setting else True

    return Response({
        'token': token.key,
        'employee': _employee_dict(emp),
        'enable_offline_mode': is_offline_mode, # 🌟 YEH LINE ADD KI HAI
    }, status=status.HTTP_200_OK)


# ==============================================================================
# 🚪 LOGOUT — Token delete karta hai
# ==============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    """
    Flutter se logout — token server pe delete ho jaata hai.
    Flutter mein bhi local storage se token hata dena.

    Success response (200):
        { "message": "Logout successful" }
    """
    try:
        request.user.auth_token.delete()
    except Exception:
        pass  # Already deleted ya exist nahi karta — koi problem nahi

    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


# ==============================================================================
# 👤 PROFILE — Apni detail
# ==============================================================================


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_team_tree(request):
    """
    Logged-in employee ki poori nested team.
    MR ke liye: empty list [] — unki koi team nahi hoti.

    Success response (200) — example RBM ke liye:
        [
            {
                "id": 3,
                "name": "Priya ABM",
                "designation": "ABM",
                "phone": "9800000001",
                "hq": "Dadar",
                "children": [
                    {
                        "id": 7,
                        "name": "Amit MR",
                        "designation": "MR",
                        "phone": "9700000001",
                        "hq": "Dadar West",
                        "children": []
                    }
                ]
            },
            ...
        ]
    """
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=status.HTTP_400_BAD_REQUEST)

    tree = get_team_tree(emp)
    return Response(_serialize_tree(tree), status=status.HTTP_200_OK)


# ==============================================================================
# 👤 PROFILE — Apni detail & Update
# ==============================================================================

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def api_profile(request):
    try:
        emp = request.user.employee
    except AttributeError:
        return Response({'error': 'Employee profile missing'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        data = _employee_dict(emp, include_manager=True)
        return Response(data, status=status.HTTP_200_OK)

    if request.method == 'PUT':
        action = request.data.get('action')

        if action == 'update_profile':
            emp.phone = request.data.get('phone', emp.phone)
            emp.address = request.data.get('address', emp.address)
            
            # 🌟 NAYA: Photo upload catch karne ka logic
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

# ==============================================================================
# 🔧 PRIVATE HELPERS
# ==============================================================================

def _employee_dict(emp, include_manager=False):
    """Employee object → Flutter-friendly dict."""
    data = {
        'id': emp.id,
        'name': emp.name,
        'designation': emp.designation,
        'phone': emp.phone or '',
        'address': emp.address or '',  # 🌟 NAYA: Address add kiya gaya
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
    """get_team_tree() ka output → JSON-serializable list."""
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
        
    # Token ko update ya create karo
    DeviceToken.objects.update_or_create(employee=emp, defaults={'token': token})
    return Response({'success': True, 'message': 'Token saved successfully!'})