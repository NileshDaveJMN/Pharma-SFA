"""
SFA/services/team.py
====================
Team scoping, territory resolution, and route lookup helpers.

Pehle ye sab auth.py mein the — ab yahan hain taaki:
  - views/auth.py  (web login)
  - api/auth.py    (Flutter login)
  - views/reports.py, sales.py, masters.py, core.py
  ...sab ek jagah se import kar sakein, duplicate code zero.

Import karo:
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
"""

from django.db.models import Q
from SFA.models import Employee, Doctor, Chemist, Territory, Route, DailyTourPlan


# ==============================================================================
# 👥 TEAM TRAVERSAL
# ==============================================================================

def get_full_team_employees(employee, include_inactive=False):
    """
    BFS down the manager→subordinate tree.
    Iterative (not recursive) — Python recursion depth se safe.

    include_inactive=False  → resigned/inactive employees skip
    include_inactive=True   → Admin screens ke liye (e.g. Data Handover dropdown)
    """
    team_ids = {employee.id}
    managers_to_check = [employee.id]

    while managers_to_check:
        subs_qs = Employee.objects.filter(manager_id__in=managers_to_check)
        if not include_inactive:
            subs_qs = subs_qs.filter(is_active=True)
        subs = list(subs_qs.values_list('id', flat=True))
        if not subs:
            break
        managers_to_check = subs
        team_ids.update(subs)

    qs = Employee.objects.filter(id__in=team_ids)
    if not include_inactive:
        qs = qs.filter(is_active=True)
    return qs


def get_data_scope(employee):
    """
    Employee jo data dekh/edit kar sakta hai uska queryset.
    MR     → sirf khud ka
    Manager → poori team ka
    """
    if employee.designation == 'MR':
        return Employee.objects.filter(id=employee.id)
    return get_full_team_employees(employee)


def get_dropdown_team(employee, ordered=True):
    """
    Report pages par employee-selector dropdown ke liye team.
    Manager → full team | MR → sirf khud

    Pehle ye pattern 8+ baar repeat hota tha har views file mein:
        if emp.designation != 'MR':
            team = get_full_team_employees(emp).order_by(...)
        else:
            team = Employee.objects.filter(id=emp.id)
    """
    if employee.designation != 'MR':
        team = get_full_team_employees(employee)
        return team.order_by('-designation', 'name') if ordered else team
    return Employee.objects.filter(id=employee.id)


def get_team_tree(employee):
    """
    🌟 Universal nested team tree — kisi bhi designation ke liye.
    Sirf 2 DB queries total (BFS + select_related).

    Returns:
        [
            {
                'emp': <Employee>,       # .name, .designation, .phone, .headquarter
                'children': [ ...same recursively... ]
            },
            ...
        ]

    Usage (profile view):
        tree = get_team_tree(employee)
        return render(request, 'profile.html', {'tree': tree})

    Flutter API usage:
        tree = get_team_tree(employee)
        return Response(_serialize_tree(tree))   # api/auth.py mein helper hai
    """
    if employee.designation == 'MR':
        return []

    all_downline = (
        get_full_team_employees(employee)
        .exclude(id=employee.id)
        .select_related('headquarter', 'manager')
        .order_by('name')
    )

    # O(n) in-memory index — koi extra DB hit nahi
    children_map = {}
    for emp in all_downline:
        if emp.manager_id:
            children_map.setdefault(emp.manager_id, []).append(emp)

    def build_node(emp):
        return {
            'emp': emp,
            'children': [build_node(c) for c in children_map.get(emp.id, [])]
        }

    return [build_node(c) for c in children_map.get(employee.id, [])]


# ==============================================================================
# 🗺️ TERRITORY & ROUTE SCOPING
# ==============================================================================

def get_team_territory_ids(team_employees):
    """
    Team ki saari relevant territories:
      - HQ territories
      - Approved doctors ki territories
      - Approved chemists ki territories
    """
    ids = set(
        team_employees
        .exclude(headquarter__isnull=True)
        .values_list('headquarter_id', flat=True)
    )
    ids.update(
        Doctor.objects
        .filter(allocated_to__in=team_employees, status='Approved')
        .values_list('territory_id', flat=True)
    )
    ids.update(
        Chemist.objects
        .filter(allocated_to__in=team_employees, status='Approved')
        .values_list('territory_id', flat=True)
    )
    ids.discard(None)
    return ids


def get_team_hq_territory_ids(team_employees):
    """
    Sirf HQ-only territories (doctor/chemist territories excluded).
    Sales.py ke stockist dropdowns ke liye.
    """
    return set(
        team_employees
        .exclude(headquarter__isnull=True)
        .values_list('headquarter_id', flat=True)
    )


def get_team_route_ids(team_employees, territory_ids, approved_only=True, include_tour_plan=False):
    """
    Team ke available route IDs.
    approved_only=True      → sirf Approved routes
    include_tour_plan=True  → MTP approved routes bhi include
    """
    qs = Route.objects.filter(territory_id__in=territory_ids)
    if approved_only:
        qs = qs.filter(status='Approved')
    ids = set(qs.values_list('id', flat=True))

    ids.update(
        Doctor.objects
        .filter(allocated_to__in=team_employees, status='Approved')
        .exclude(route__isnull=True)
        .values_list('route_id', flat=True)
    )
    ids.update(
        Chemist.objects
        .filter(allocated_to__in=team_employees, status='Approved')
        .exclude(route__isnull=True)
        .values_list('route_id', flat=True)
    )
    if include_tour_plan:
        ids.update(
            DailyTourPlan.objects
            .filter(mtp__employee__in=team_employees, mtp__status='Approved')
            .values_list('route_id', flat=True)
        )
    ids.discard(None)
    return ids


def get_team_requested_routes(team_employees, territory_ids):
    """
    Team ki territories ke routes + team ne khud request kiye routes.
    Route reports ke liye.
    """
    return (
        Route.objects
        .filter(
            Q(territory_id__in=territory_ids) |
            Q(requested_by__in=team_employees)
        )
        .select_related('territory', 'requested_by')
        .distinct()
        .order_by('name')
    )


def get_own_territories_and_routes(employee):
    """
    Ek single employee ki apni territories aur routes.
    Returns: (territories_queryset, routes_queryset)
    """
    t_ids = set()
    if employee.headquarter_id:
        t_ids.add(employee.headquarter_id)

    t_ids.update(
        Doctor.objects
        .filter(allocated_to=employee, status='Approved')
        .values_list('territory_id', flat=True)
    )
    t_ids.update(
        Chemist.objects
        .filter(allocated_to=employee, status='Approved')
        .values_list('territory_id', flat=True)
    )
    t_ids.discard(None)

    territories = Territory.objects.filter(id__in=t_ids).order_by('name')
    routes = (
        Route.objects
        .filter(Q(territory_id__in=t_ids) | Q(requested_by=employee))
        .select_related('territory')
        .distinct()
        .order_by('name')
    )
    return territories, routes
