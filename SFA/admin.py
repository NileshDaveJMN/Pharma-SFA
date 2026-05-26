from django.contrib import admin
from .models import (
    Territory, Employee, Stockist, Chemist, Doctor, Product, 
    PrimarySale, SecondarySale, RCPA_Audit, Route, 
    MonthlyTourProgram, DailyTourPlan, 
    DailyDCR, DCRVisit, DCRProductDetail, DayEnd, DayStart
)

# ==========================================
# MASTER TABLES (Optimized)
# ==========================================
@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory')
    list_filter = ('territory',)
    
    # PERFORMANCE FIX: Pre-fetch territory to avoid N+1
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('territory')

@admin.register(Territory)
class TerritoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee_code', 'designation', 'manager', 'headquarter')
    list_filter = ('designation', 'headquarter')
    search_fields = ('name', 'employee_code')
    
    # PERFORMANCE FIX: Pre-fetch manager and headquarter
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('manager', 'headquarter')

@admin.register(Stockist)
class StockistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory')
    
    # PERFORMANCE FIX
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('territory')

@admin.register(Chemist)
class ChemistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory', 'route', 'allocated_to')
    list_filter = ('territory', 'route', 'allocated_to')
    
    # PERFORMANCE FIX: Pre-fetch territory, route, allocated_to
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('territory', 'route', 'allocated_to')

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialty', 'territory', 'route', 'allocated_to')
    list_filter = ('territory', 'route', 'allocated_to')
    
    # PERFORMANCE FIX: Pre-fetch territory, route, allocated_to
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('territory', 'route', 'allocated_to')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'pack_size', 'price')


# ==========================================
# TOUR PROGRAM (Optimized Master & Detail Admin)
# ==========================================

class DailyTourPlanInline(admin.TabularInline):
    model = DailyTourPlan
    extra = 0 # Extra empty rows reduce karne ke liye 0 set kiya
    
    # Inline ke liye route pre-fetch karein
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('route')

@admin.register(MonthlyTourProgram)
class MonthlyTourProgramAdmin(admin.ModelAdmin):
    list_display = ('date_month_year', 'employee', 'status')
    list_filter = ('status', 'month', 'year', 'employee')
    list_editable = ('status',)
    inlines = [DailyTourPlanInline]
    
    # PERFORMANCE FIX: Pre-fetch employee in list view
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('employee')
    
    # List view mein month/year ache se dikhane ke liye custom function
    def date_month_year(self, obj):
        return f"{obj.month}/{obj.year}"
    date_month_year.short_description = 'Month/Year'


# ==========================================
# DCR & DAY TRACKING (Optimized Master-Detail)
# ==========================================

class DCRVisitInline(admin.TabularInline):
    model = DCRVisit
    extra = 0 # Extra empty rows reduce karne ke liye 0 set kiya
    
    # Inline ke liye related doctor, chemist pre-fetch karein
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('doctor', 'chemist')

@admin.register(DailyDCR)
class DailyDCRAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee')
    list_filter = ('date', 'employee')
    inlines = [DCRVisitInline] 
    
    # PERFORMANCE FIX: Pre-fetch employee in list view
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('employee')

@admin.register(DCRVisit)
class DCRVisitAdmin(admin.ModelAdmin):
    list_display = ('date_dcr', 'employee_dcr', 'target_name')
    list_filter = ('daily_dcr__date', 'daily_dcr__employee')
    
    # PERFORMANCE FIX: Pre-fetch sab kuch takay list main sub optimized ho
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('daily_dcr', 'daily_dcr__employee', 'doctor', 'chemist')
    
    # Custom display functions
    def date_dcr(self, obj):
        return obj.daily_dcr.date
    date_dcr.short_description = 'Date'
    
    def employee_dcr(self, obj):
        return obj.daily_dcr.employee.name
    employee_dcr.short_description = 'Employee'
    
    def target_name(self, obj):
        return obj.doctor.name if obj.doctor else obj.chemist.name
    target_name.short_description = 'Doctor/Chemist'


@admin.register(DayEnd)
class DayEndAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_closed')
    list_filter = ('date', 'employee', 'is_closed')
    
    # PERFORMANCE FIX
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('employee')

# DayStart optimized
@admin.register(DayStart)
class DayStartAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'territory')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('employee', 'territory')
