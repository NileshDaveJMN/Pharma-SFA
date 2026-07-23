from django.contrib import admin
from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import (
    Company,
    Territory, Employee, Stockist, Chemist, Doctor, Product,
    PrimarySale, SecondarySale, RCPA_Audit, Route,
    MonthlyTourProgram, DailyTourPlan,
    DailyDCR, DCRVisit, DCRProductDetail, DayEnd, DayStart,
    MonthlyExpenseReport, DailyExpense, StockistProductStatement,
    DARate, TARate, DoctorChemistProductMapping, PharmaActivity,
    PartyWiseSaleReport, PartyWiseSaleLine, DoctorRxMapping,
    TerritoryTarget, MonthlyTargetMaster, Holiday, LeaveBalance, 
    LeaveApplication, HQDistance, CompanyNotice, SystemNotification, DirectMessage,
    DailyDCRStatus,
    reverse_visit_inventory, DoctorEditRequest, ChemistEditRequest,
)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'slug', 'subscription_plan', 'subscription_expiry', 'max_users', 'is_active')
    list_filter = ('is_active', 'subscription_plan')
    search_fields = ('name', 'code', 'slug')
    prepopulated_fields = {'slug': ('code',)}
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'code', 'slug', 'is_active', 'logo'),
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'address'),
        }),
        ('Settings', {
            'fields': ('financial_year_start', 'currency', 'timezone'),
        }),
        ('Subscription', {
            'fields': ('subscription_plan', 'subscription_expiry', 'max_users'),
        }),
    )

from .models import PromoItem, PromoDispatch, MRInventory, GiftCampaignPlan, DoctorROILedger, FreeQtyClaimMaster, FreeQtyClaimLine

# ── Reusable Company Assignment Mixin ────────────────────────────────────────
class AssignCompanyMixin:
    """Add this mixin to any ModelAdmin to get bulk 'Assign Company' action."""
    actions = ['assign_company']

    @admin.action(description='🏢 Assign Company to selected records')
    def assign_company(self, request, queryset):
        if 'apply' in request.POST:
            company_id = request.POST.get('company')
            if company_id:
                updated = queryset.update(company_id=company_id)
                self.message_user(request, f'✅ {updated} records ko company assign ho gayi!', messages.SUCCESS)
            else:
                self.message_user(request, '❌ Koi company select nahi ki!', messages.ERROR)
            return None

        companies = Company.objects.filter(is_active=True)
        return render(request, 'admin/assign_company.html', {
            'queryset': queryset,
            'companies': companies,
            'action': 'assign_company',
            'opts': self.model._meta,
        })



admin.site.register(PromoItem)
admin.site.register(PromoDispatch)
admin.site.register(MRInventory)
admin.site.register(GiftCampaignPlan)
admin.site.register(DoctorROILedger)

# ==========================================
# MASTER TABLES (Optimized)
# ==========================================
@admin.register(Route)
class RouteAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'territory', 'category', 'distance_from_hq', 'status')
    list_filter = ('territory', 'category', 'status')
    list_editable = ('category', 'distance_from_hq', 'status')
    search_fields = ('name',)
    ordering = ('territory', 'category', 'name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('territory')

@admin.register(Territory)
class TerritoryAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'city')
    search_fields = ('name', 'city')
    ordering = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    # 🌟 Naye fields list_display me add kiye (is_active)
    list_display = ('id', 'name', 'employee_code', 'designation', 'is_active', 'manager', 'headquarter', 'joining_date')
    
    # 🌟 Naya filter (Active/Inactive)
    list_filter = ('is_active', 'designation', 'headquarter')
    search_fields = ('name', 'employee_code', 'user__username')
    
    # Optional: is_active ko bahar grid se hi click karke change karne ki permission
    list_editable = ('is_active',) 

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('manager', 'headquarter', 'user')

    # 🛑 ADMIN ACTION: Ek click mein Soft-Delete / Deactivate karein
    actions = ['deactivate_employees']

    @admin.action(description='Mark selected employees as Inactive (Block Login)')
    def deactivate_employees(self, request, queryset):
        from django.utils import timezone
        
        updated_count = 0
        for emp in queryset:
            if emp.is_active:
                # 1. Employee ko inactive karo
                emp.is_active = False
                emp.leaving_date = timezone.now().date()
                emp.save()
                
                # 2. Django User (Login) ko bhi block karo
                if emp.user:
                    emp.user.is_active = False
                    emp.user.save()
                    
                updated_count += 1
                
        self.message_user(request, f"Success: {updated_count} employees aur unke login accounts ko Inactive kar diya gaya hai.")

@admin.register(Stockist)
class StockistAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'territory', 'contact_person', 'phone')
    search_fields = ('name', 'phone')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('territory')

@admin.register(Chemist)
class ChemistAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'territory', 'route', 'allocated_to', 'status')
    list_filter = ('territory', 'route', 'allocated_to', 'status')
    search_fields = ('name', 'phone')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('territory', 'route', 'allocated_to')

@admin.register(Doctor)
class DoctorAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'specialty', 'territory', 'route', 'allocated_to', 'status')
    list_filter = ('territory', 'route', 'allocated_to', 'specialty', 'status')
    search_fields = ('name', 'specialty')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('territory', 'route', 'allocated_to')

@admin.register(Product)
class ProductAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'pack_size', 'price')
    search_fields = ('name',)


# ==========================================
# EXPENSE MANAGEMENT
# ==========================================
class DailyExpenseInline(admin.TabularInline):
    model = DailyExpense
    extra = 0
    readonly_fields = ('created_at',) 

@admin.register(MonthlyExpenseReport)
class MonthlyExpenseReportAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'status', 'is_modified')
    list_filter = ('status', 'month', 'year', 'is_modified', 'employee')
    list_editable = ('status',)
    inlines = [DailyExpenseInline]
    search_fields = ('employee__name',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee')


# ==========================================
# TOUR PROGRAM
# ==========================================
class DailyTourPlanInline(admin.TabularInline):
    model = DailyTourPlan
    extra = 0 
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('route')

@admin.register(MonthlyTourProgram)
class MonthlyTourProgramAdmin(admin.ModelAdmin):
    list_display = ('date_month_year', 'employee', 'status', 'is_modified')
    list_filter = ('status', 'month', 'year', 'is_modified', 'employee')
    list_editable = ('status',)
    inlines = [DailyTourPlanInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee')
    
    def date_month_year(self, obj):
        return f"{obj.month}/{obj.year}"
    date_month_year.short_description = 'Month/Year'


# ==========================================
# 🚀 SMART DCR & DAY TRACKING (Merged Logic)
# ==========================================
class DCRProductDetailInline(admin.TabularInline):
    model = DCRProductDetail
    extra = 0
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

class DCRVisitInline(admin.TabularInline):
    model = DCRVisit
    extra = 0 
    readonly_fields = ('latitude', 'longitude', 'created_at')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('doctor', 'chemist')

# ==========================================
# 🚀 SMART DCR & DAY TRACKING (Merged Logic)
# ==========================================
@admin.register(DailyDCR)
class DailyDCRAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'created_at')
    list_filter = ('date', 'employee')
    search_fields = ('employee__name', 'date')
    inlines = [DCRVisitInline] 
    readonly_fields = ('created_at',)
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee')

    # 1. Single Delete Override
    def delete_model(self, request, obj):
        with transaction.atomic():
            emp = obj.employee
            target_date = obj.date
            for visit in obj.visits.all():
                reverse_visit_inventory(visit)  # 🔄 Inventory + ROI wapas reverse karo
            DayStart.objects.filter(employee=emp, date=target_date).delete()
            DayEnd.objects.filter(employee=emp, date=target_date).delete()
            DailyExpense.objects.filter(employee=emp, date=target_date).delete()  # 🔥 EXPENSE BHI DELETE HOGA
            DailyDCRStatus.objects.filter(employee=emp, date=target_date).delete() # 🌟 NAYA: STATUS BHI DELETE HOGA!
            obj.visits.all().delete()
            super().delete_model(request, obj)

    # 2. Bulk Delete Override
    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                emp = obj.employee
                target_date = obj.date
                for visit in obj.visits.all():
                    reverse_visit_inventory(visit)  # 🔄 Inventory + ROI wapas reverse karo
                DayStart.objects.filter(employee=emp, date=target_date).delete()
                DayEnd.objects.filter(employee=emp, date=target_date).delete()
                DailyExpense.objects.filter(employee=emp, date=target_date).delete()  # 🔥 EXPENSE BHI DELETE HOGA
                DailyDCRStatus.objects.filter(employee=emp, date=target_date).delete() # 🌟 NAYA: STATUS BHI DELETE HOGA!
                obj.visits.all().delete()
            super().delete_queryset(request, queryset)


@admin.register(DCRVisit)
class DCRVisitAdmin(admin.ModelAdmin):
    list_display = ('date_dcr', 'employee_dcr', 'target_name')
    list_filter = ('daily_dcr__date', 'daily_dcr__employee')
    inlines = [DCRProductDetailInline]
    readonly_fields = ('latitude', 'longitude', 'created_at')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('daily_dcr', 'daily_dcr__employee', 'doctor', 'chemist')
    
    def date_dcr(self, obj):
        return obj.daily_dcr.date
    date_dcr.short_description = 'Date'
    
    def employee_dcr(self, obj):
        return obj.daily_dcr.employee.name
    employee_dcr.short_description = 'Employee'
    
    def target_name(self, obj):
        return obj.doctor.name if obj.doctor else obj.chemist.name
    target_name.short_description = 'Doctor/Chemist'

    # 🔄 Agar koi visit yahan se DIRECTLY delete ho (DailyDCR ke through nahi),
    # to bhi inventory/ROI sahi se reverse hona chahiye.
    def delete_model(self, request, obj):
        with transaction.atomic():
            reverse_visit_inventory(obj)
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                reverse_visit_inventory(obj)
            super().delete_queryset(request, queryset)

@admin.register(DayEnd)
class DayEndAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_closed', 'closed_at')
    list_filter = ('date', 'employee', 'is_closed')
    readonly_fields = ('latitude', 'longitude', 'closed_at')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee')

@admin.register(DayStart)
class DayStartAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'territory', 'started_at')
    list_filter = ('date', 'employee', 'territory')
    readonly_fields = ('latitude', 'longitude', 'started_at')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee', 'territory')


# ==========================================
# SALES & AUDIT
# ==========================================
@admin.register(PrimarySale)
class PrimarySaleAdmin(admin.ModelAdmin):
    list_display = ('date', 'stockist', 'product', 'quantity', 'batch_number')
    list_filter = ('date', 'stockist')
    search_fields = ('stockist__name', 'product__name')

@admin.register(SecondarySale)
class SecondarySaleAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'stockist', 'chemist', 'product', 'quantity')
    list_filter = ('date', 'employee', 'stockist')
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee', 'stockist', 'chemist', 'product')

@admin.register(RCPA_Audit)
class RCPA_AuditAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'doctor', 'chemist', 'product', 'quantity_prescribed')
    list_filter = ('date', 'employee')
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employee', 'doctor', 'chemist', 'product')

@admin.register(StockistProductStatement)
class StockistProductStatementAdmin(admin.ModelAdmin):
    list_display = ('stockist', 'product', 'month', 'year', 'opening_qty', 'sale_qty')
    list_filter = ('month', 'year', 'stockist')
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('stockist', 'product', 'employee')


# ==========================================
# DA / TA RATE TABLES
# ==========================================
@admin.register(DARate)
class DARateAdmin(admin.ModelAdmin):
    list_display = ('designation', 'hq_da', 'exhq_da', 'outstation_da')
    ordering = ('designation',)

@admin.register(TARate)
class TARateAdmin(admin.ModelAdmin):
    list_display  = ('designation', 'slab1_upto_km', 'slab1_rate', 'slab2_upto_km', 'slab2_rate')
    list_editable = ('slab1_upto_km', 'slab1_rate', 'slab2_upto_km', 'slab2_rate')
    ordering      = ('designation',)


# ==========================================
# DOCTOR CHEMIST MAPPING & ACTIVITY
# ==========================================
@admin.register(DoctorChemistProductMapping)
class DoctorChemistProductMappingAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'chemist', 'product')
    list_filter = ('doctor', 'chemist', 'product')
    search_fields = ('doctor__name', 'chemist__name', 'product__name')

@admin.register(PharmaActivity)
class PharmaActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'employee', 'doctor', 'status', 'created_at')
    list_filter = ('status', 'employee')
    search_fields = ('title', 'doctor__name')


# ==========================================
# PARTY WISE SALE & RX CLASSIFICATION
# ==========================================
class PartyWiseSaleLineInline(admin.TabularInline):
    model = PartyWiseSaleLine
    extra = 0

@admin.register(PartyWiseSaleReport)
class PartyWiseSaleReportAdmin(admin.ModelAdmin):
    list_display = ('stockist', 'employee', 'month', 'year', 'created_at')
    list_filter = ('month', 'year', 'stockist', 'employee')
    inlines = [PartyWiseSaleLineInline]

@admin.register(DoctorRxMapping)
class DoctorRxMappingAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'party_line', 'mapped_billed_qty', 'mapped_free_qty')
    search_fields = ('doctor__name', 'party_line__product__name')


# ==========================================
# TARGET SETTING & APPROVAL MASTERS
# ==========================================
@admin.register(TerritoryTarget)
class TerritoryTargetAdmin(admin.ModelAdmin):
    list_display = ('territory', 'product', 'month', 'year', 'target_qty', 'target_value')
    list_filter = ('territory', 'month', 'year')
    search_fields = ('territory__name', 'product__name')

@admin.register(MonthlyTargetMaster)
class MonthlyTargetMasterAdmin(admin.ModelAdmin):
    list_display = ('territory', 'month', 'year', 'status')
    list_filter = ('status', 'month', 'year', 'territory')
    list_editable = ('status',) 
    search_fields = ('territory__name',)


# ==========================================
# 🏖️ HOLIDAY & LEAVE MANAGEMENT
# ==========================================
@admin.register(Holiday)
class HolidayAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'date', 'proposed_by', 'status')
    list_filter = ('status', 'date')
    list_editable = ('status',) 
    search_fields = ('name',)

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'year', 'cl_total', 'sl_total', 'pl_total', 'cl_used', 'sl_used', 'pl_used')
    search_fields = ('employee__name',)
    list_editable = ('cl_total', 'sl_total', 'pl_total') 
    list_filter = ('year',)

@admin.register(LeaveApplication)
class LeaveApplicationAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'no_of_days', 'status', 'applied_on')
    list_filter = ('status', 'leave_type', 'start_date')
    search_fields = ('employee__name',)


# ==========================================
# MISCELLANEOUS & COMMUNICATIONS
# ==========================================
admin.site.register(HQDistance)
admin.site.register(CompanyNotice)
admin.site.register(SystemNotification)
admin.site.register(DirectMessage)

from SFA.models import SystemSetting

# admin.py ke top imports mein DailyDCRStatus add kar lena
from .models import DailyDCRStatus

# ==========================================
# 📅 CALENDAR STATUS ADMIN (FOR UNLOCKING)
# ==========================================
@admin.register(DailyDCRStatus)
class DailyDCRStatusAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'day_type', 'is_open', 'is_submitted', 'is_admin_unlocked', 'unlocked_until')
    list_filter = ('is_open', 'is_submitted', 'is_admin_unlocked', 'date', 'employee')
    list_editable = ('is_open', 'is_admin_unlocked') # 🌟 Yahan se Admin seedha Tick karke unlock karega! (1 din ke liye valid rahega)
    search_fields = ('employee__name',)
    ordering = ('-date', 'employee')


# ==========================================
# ⚙️ MASTER SETTINGS OVERRIDE
# ==========================================
@admin.register(SystemSetting)
class SystemSettingAdmin(AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('__str__', 'enable_offline_mode', 'dcr_lock_days', 'without_tourplan_dcr_block', 'allow_current_month_mtp', 'strict_geofence_for_backdate')
    
    fieldsets = (
        ('General & App Settings', {
            'fields': ('allow_location_capture', 'enable_offline_mode', 'strict_geofence_for_backdate'),
        }),
        ('Deadlines (Numeric Rules)', {
            'fields': ('dcr_lock_days', 'mtp_approval_deadline_day', 'expense_submit_deadline_day', 'sale_upload_deadline_day', 'free_claim_deadline_day', 'target_approval_deadline_day'),
        }),
        ('Strict Blocker Switches', {
            'fields': ('without_tourplan_dcr_block', 'manager_pending_approval_block'),
        }),
        ('Exception / Testing Switches', {
            'fields': ('allow_current_month_mtp',),
            'description': 'These settings are for temporary exceptions only — turn OFF once work is done.',
        }),
    )

    def has_add_permission(self, request):
        if self.model.objects.exists(): return False
        return super().has_add_permission(request)
class FreeQtyClaimLineInline(admin.TabularInline):
    model = FreeQtyClaimLine
    extra = 0
    readonly_fields = ('product', 'total_billed_qty', 'total_free_qty', 'claim_value')

@admin.register(FreeQtyClaimMaster)
class FreeQtyClaimMasterAdmin(admin.ModelAdmin):
    list_display = ('employee', 'stockist', 'month', 'year', 'status', 'created_at')
    list_filter = ('status', 'month', 'year', 'employee')
    search_fields = ('employee__name', 'stockist__name')
    inlines = [FreeQtyClaimLineInline]
    
# ==========================================
# ✏️ EDIT REQUESTS ADMIN
# ==========================================
@admin.register(DoctorEditRequest)
class DoctorEditRequestAdmin(admin.ModelAdmin):
    list_display = ('doctor', 'req_name', 'employee', 'status', 'created_at')
    list_filter = ('status', 'employee')
    search_fields = ('doctor__name', 'req_name', 'employee__name')
    readonly_fields = ('created_at',)

@admin.register(ChemistEditRequest)
class ChemistEditRequestAdmin(admin.ModelAdmin):
    list_display = ('chemist', 'req_name', 'employee', 'status', 'created_at')
    list_filter = ('status', 'employee')
    search_fields = ('chemist__name', 'req_name', 'employee__name')
    readonly_fields = ('created_at',)
