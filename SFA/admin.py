from django.contrib import admin
from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import (
    Company, Territory, Employee, Stockist, Chemist, Doctor, Product,
    PrimarySale, SecondarySale, RCPA_Audit, Route,
    MonthlyTourProgram, DailyTourPlan,
    DailyDCR, DCRVisit, DCRProductDetail, DayEnd, DayStart,
    MonthlyExpenseReport, DailyExpense, StockistProductStatement,
    DARate, TARate, DoctorChemistProductMapping, PharmaActivity,
    PartyWiseSaleReport, PartyWiseSaleLine, DoctorRxMapping,
    TerritoryTarget, MonthlyTargetMaster, Holiday, LeaveBalance, 
    LeaveApplication, HQDistance, CompanyNotice, SystemNotification, DirectMessage,
    DailyDCRStatus, reverse_visit_inventory, DoctorEditRequest, ChemistEditRequest,
    PromoItem, PromoDispatch, MRInventory, GiftCampaignPlan, DoctorROILedger, FreeQtyClaimMaster, FreeQtyClaimLine
)
from SFA.models import SystemSetting

# ==============================================================================
# 🛡️ SAAS SECURITY MIXIN (THE MAGIC GUARD)
# Ye ensure karega ki kisi bhi Company Admin ko doosri company ka data na dikhe
# ==============================================================================
class TenantIsolationMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # 1. Agar Superuser (Aap) hain, toh saara data dikhega
        if request.user.is_superuser:
            return qs
        
        # 2. Agar Company Admin hai, toh uski company filter karo
        try:
            admin_company = request.user.employee.company
            if hasattr(self.model, 'company'):
                return qs.filter(company=admin_company)
            elif hasattr(self.model, 'employee'):
                return qs.filter(employee__company=admin_company)
            elif hasattr(self.model, 'territory'):
                return qs.filter(territory__company=admin_company)
            elif hasattr(self.model, 'stockist'):
                return qs.filter(stockist__company=admin_company)
            elif hasattr(self.model, 'doctor'):
                return qs.filter(doctor__company=admin_company)
        except Exception:
            return qs.none() # Error aane par list khali dikhegi
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # 3. Dropdowns (Select box) mein bhi sirf apni company ka data dikhega
        if not request.user.is_superuser:
            try:
                admin_company = request.user.employee.company
                if db_field.name in ["employee", "manager", "allocated_to", "proposed_by", "sender", "receiver"]:
                    kwargs["queryset"] = Employee.objects.filter(company=admin_company)
                elif db_field.name == "doctor":
                    kwargs["queryset"] = Doctor.objects.filter(company=admin_company)
                elif db_field.name == "chemist":
                    kwargs["queryset"] = Chemist.objects.filter(company=admin_company)
                elif db_field.name == "stockist":
                    kwargs["queryset"] = Stockist.objects.filter(company=admin_company)
                elif db_field.name in ["territory", "from_territory", "to_territory", "headquarter"]:
                    kwargs["queryset"] = Territory.objects.filter(company=admin_company)
                elif db_field.name == "route":
                    kwargs["queryset"] = Route.objects.filter(company=admin_company)
                elif db_field.name in ["product", "item", "linked_product"]:
                    kwargs["queryset"] = db_field.related_model.objects.filter(company=admin_company)
                elif db_field.name == "company":
                    kwargs["queryset"] = Company.objects.filter(id=admin_company.id)
            except Exception:
                pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


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


# ==========================================
# 🏢 SUPER ADMIN ONLY MODELS (No Tenant Mixin)
# ==========================================
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'slug', 'subscription_plan', 'subscription_expiry', 'max_users', 'is_active')
    list_filter = ('is_active', 'subscription_plan')
    search_fields = ('name', 'code', 'slug')
    prepopulated_fields = {'slug': ('code',)}
    list_editable = ('is_active', 'subscription_plan')
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'code', 'slug', 'is_active', 'logo')}),
        ('Contact', {'fields': ('email', 'phone', 'address')}),
        ('Settings', {'fields': ('financial_year_start', 'currency', 'timezone')}),
        ('Subscription', {'fields': ('subscription_plan', 'subscription_expiry', 'max_users')}),
    )

# ==========================================
# 🎁 MODELS ACCESSIBLE TO COMPANY ADMINS (With Tenant Mixin)
# ==========================================

# --- Promo & Inventory ---
@admin.register(PromoItem)
class PromoItemAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'item_type', 'price', 'is_active')

@admin.register(PromoDispatch)
class PromoDispatchAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('item', 'employee', 'quantity', 'status')

@admin.register(MRInventory)
class MRInventoryAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'item', 'stock_qty')

@admin.register(GiftCampaignPlan)
class GiftCampaignPlanAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'doctor', 'item', 'month', 'year', 'status')

@admin.register(DoctorROILedger)
class DoctorROILedgerAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('doctor', 'employee', 'item', 'quantity', 'total_value', 'date_given')

# --- Masters ---
@admin.register(Route)
class RouteAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'territory', 'category', 'distance_from_hq', 'status')
    list_filter = ('territory', 'category', 'status')
    list_editable = ('category', 'distance_from_hq', 'status')
    search_fields = ('name',)
    ordering = ('territory', 'category', 'name')
    def get_queryset(self, request): return super().get_queryset(request).select_related('territory')

@admin.register(Territory)
class TerritoryAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'city')
    search_fields = ('name', 'city')
    ordering = ('name',)

@admin.register(Employee)
class EmployeeAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'employee_code', 'designation', 'is_active', 'manager', 'headquarter', 'joining_date')
    list_filter = ('is_active', 'designation', 'headquarter')
    search_fields = ('name', 'employee_code', 'user__username')
    list_editable = ('is_active',) 
    actions = ['deactivate_employees']
    def get_queryset(self, request): return super().get_queryset(request).select_related('manager', 'headquarter', 'user')
    @admin.action(description='Mark selected employees as Inactive (Block Login)')
    def deactivate_employees(self, request, queryset):
        from django.utils import timezone
        updated_count = 0
        for emp in queryset:
            if emp.is_active:
                emp.is_active = False
                emp.leaving_date = timezone.now().date()
                emp.save()
                if emp.user:
                    emp.user.is_active = False
                    emp.user.save()
                updated_count += 1
        self.message_user(request, f"Success: {updated_count} employees and accounts deactivated.")

@admin.register(Stockist)
class StockistAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'territory', 'contact_person', 'phone')
    search_fields = ('name', 'phone')
    def get_queryset(self, request): return super().get_queryset(request).select_related('territory')

@admin.register(Chemist)
class ChemistAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    # 🌟 DEBUG FIX: 'company' column + filter add kiya taaki blank-company
    # records shell ke bina hi list view me pakde ja sakein
    list_display = ('name', 'company', 'territory', 'route', 'allocated_to', 'status')
    list_filter = ('company', 'territory', 'route', 'status')
    search_fields = ('name', 'phone')
    def get_queryset(self, request): return super().get_queryset(request).select_related('company', 'territory', 'route', 'allocated_to')

@admin.register(Doctor)
class DoctorAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    # 🌟 DEBUG FIX: 'company' column + filter add kiya taaki blank-company
    # records shell ke bina hi list view me pakde ja sakein
    list_display = ('name', 'company', 'specialty', 'territory', 'route', 'allocated_to', 'status')
    list_filter = ('company', 'territory', 'route', 'specialty', 'status')
    search_fields = ('name', 'specialty')
    def get_queryset(self, request): return super().get_queryset(request).select_related('company', 'territory', 'route', 'allocated_to')

@admin.register(Product)
class ProductAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'pack_size', 'price')
    search_fields = ('name',)

# --- Daily Operations & Smart DCR ---
class DCRProductDetailInline(admin.TabularInline):
    model = DCRProductDetail
    extra = 0
    def get_queryset(self, request): return super().get_queryset(request).select_related('product')

class DCRVisitInline(admin.TabularInline):
    model = DCRVisit
    extra = 0 
    readonly_fields = ('latitude', 'longitude', 'created_at')
    def get_queryset(self, request): return super().get_queryset(request).select_related('doctor', 'chemist')

@admin.register(DailyDCR)
class DailyDCRAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date', 'employee', 'created_at')
    list_filter = ('date',)
    search_fields = ('employee__name', 'date')
    inlines = [DCRVisitInline] 
    readonly_fields = ('created_at',)
    def get_queryset(self, request): return super().get_queryset(request).select_related('employee')

    def delete_model(self, request, obj):
        with transaction.atomic():
            emp = obj.employee
            target_date = obj.date
            for visit in obj.visits.all(): reverse_visit_inventory(visit)
            DayStart.objects.filter(employee=emp, date=target_date).delete()
            DayEnd.objects.filter(employee=emp, date=target_date).delete()
            DailyExpense.objects.filter(employee=emp, date=target_date).delete()
            DailyDCRStatus.objects.filter(employee=emp, date=target_date).delete()
            obj.visits.all().delete()
            super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset:
                emp = obj.employee
                target_date = obj.date
                for visit in obj.visits.all(): reverse_visit_inventory(visit)
                DayStart.objects.filter(employee=emp, date=target_date).delete()
                DayEnd.objects.filter(employee=emp, date=target_date).delete()
                DailyExpense.objects.filter(employee=emp, date=target_date).delete()
                DailyDCRStatus.objects.filter(employee=emp, date=target_date).delete()
                obj.visits.all().delete()
            super().delete_queryset(request, queryset)

@admin.register(DCRVisit)
class DCRVisitAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date_dcr', 'employee_dcr', 'target_name')
    inlines = [DCRProductDetailInline]
    readonly_fields = ('latitude', 'longitude', 'created_at')
    def get_queryset(self, request): return super().get_queryset(request).select_related('daily_dcr', 'daily_dcr__employee', 'doctor', 'chemist')
    def date_dcr(self, obj): return obj.daily_dcr.date
    def employee_dcr(self, obj): return obj.daily_dcr.employee.name
    def target_name(self, obj): return obj.doctor.name if obj.doctor else (obj.chemist.name if obj.chemist else 'N/A')
    def delete_model(self, request, obj):
        with transaction.atomic():
            reverse_visit_inventory(obj)
            super().delete_model(request, obj)
    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            for obj in queryset: reverse_visit_inventory(obj)
            super().delete_queryset(request, queryset)

@admin.register(DayEnd)
class DayEndAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_closed', 'closed_at')
    readonly_fields = ('latitude', 'longitude', 'closed_at')
    
@admin.register(DayStart)
class DayStartAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'date', 'territory', 'started_at')
    readonly_fields = ('latitude', 'longitude', 'started_at')

# --- Expense & MTP ---
class DailyExpenseInline(admin.TabularInline):
    model = DailyExpense
    extra = 0
    readonly_fields = ('created_at',) 

@admin.register(MonthlyExpenseReport)
class MonthlyExpenseReportAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'status', 'is_modified')
    list_editable = ('status',)
    inlines = [DailyExpenseInline]

class DailyTourPlanInline(admin.TabularInline):
    model = DailyTourPlan
    extra = 0 

@admin.register(MonthlyTourProgram)
class MonthlyTourProgramAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date_month_year', 'employee', 'status', 'is_modified')
    list_editable = ('status',)
    inlines = [DailyTourPlanInline]
    def date_month_year(self, obj): return f"{obj.month}/{obj.year}"

# --- Sales, Audit & Statements ---
@admin.register(PrimarySale)
class PrimarySaleAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date', 'stockist', 'product', 'quantity', 'batch_number')

@admin.register(SecondarySale)
class SecondarySaleAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date', 'employee', 'stockist', 'chemist', 'product', 'quantity')

@admin.register(RCPA_Audit)
class RCPA_AuditAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('date', 'employee', 'doctor', 'chemist', 'product', 'quantity_prescribed')

@admin.register(StockistProductStatement)
class StockistProductStatementAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('stockist', 'product', 'month', 'year', 'opening_qty', 'sale_qty')

# --- DA / TA Rates ---
@admin.register(DARate)
class DARateAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('designation', 'hq_da', 'exhq_da', 'outstation_da')
    ordering = ('designation',)

@admin.register(TARate)
class TARateAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display  = ('designation', 'slab1_upto_km', 'slab1_rate', 'slab2_upto_km', 'slab2_rate')
    list_editable = ('slab1_upto_km', 'slab1_rate', 'slab2_upto_km', 'slab2_rate')
    ordering      = ('designation',)

# --- Targets & Party Wise ---
class PartyWiseSaleLineInline(admin.TabularInline):
    model = PartyWiseSaleLine
    extra = 0

@admin.register(PartyWiseSaleReport)
class PartyWiseSaleReportAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('stockist', 'employee', 'month', 'year', 'created_at')
    inlines = [PartyWiseSaleLineInline]

@admin.register(DoctorRxMapping)
class DoctorRxMappingAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('doctor', 'party_line', 'mapped_billed_qty', 'mapped_free_qty')

@admin.register(TerritoryTarget)
class TerritoryTargetAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('territory', 'product', 'month', 'year', 'target_qty', 'target_value')

@admin.register(MonthlyTargetMaster)
class MonthlyTargetMasterAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('territory', 'month', 'year', 'status')
    list_editable = ('status',) 

# --- Settings, Holidays & Leave ---
@admin.register(Holiday)
class HolidayAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('name', 'date', 'proposed_by', 'status')
    list_editable = ('status',) 

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'year', 'cl_total', 'sl_total', 'pl_total', 'cl_used', 'sl_used', 'pl_used')
    list_editable = ('cl_total', 'sl_total', 'pl_total') 

@admin.register(LeaveApplication)
class LeaveApplicationAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'no_of_days', 'status')

@admin.register(SystemSetting)
class SystemSettingAdmin(TenantIsolationMixin, AssignCompanyMixin, admin.ModelAdmin):
    list_display = ('__str__', 'company', 'enable_offline_mode', 'dcr_lock_days', 'without_tourplan_dcr_block')
    list_filter = ('company',)
    fieldsets = (
        ('General & App Settings', {'fields': ('company', 'allow_location_capture', 'enable_offline_mode', 'strict_geofence_for_backdate', 'allow_mr_primary_sale')}),
        ('Deadlines (Numeric Rules)', {'fields': ('dcr_lock_days', 'mtp_approval_deadline_day', 'expense_submit_deadline_day', 'sale_upload_deadline_day', 'free_claim_deadline_day', 'target_approval_deadline_day')}),
        ('Strict Blocker Switches', {'fields': ('without_tourplan_dcr_block', 'manager_pending_approval_block')}),
        ('Exception / Testing Switches', {'fields': ('allow_current_month_mtp',), 'description': 'Testing exception switches.'}),
    )
    def has_add_permission(self, request): return super().has_add_permission(request)

# --- Misc & Claims ---
@admin.register(HQDistance)
class HQDistanceAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('from_territory', 'to_territory', 'distance_km')

@admin.register(CompanyNotice)
class CompanyNoticeAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('title', 'created_by', 'is_active', 'created_at')

@admin.register(SystemNotification)
class SystemNotificationAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'title', 'is_read', 'created_at')

@admin.register(DirectMessage)
class DirectMessageAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'is_read', 'created_at')

@admin.register(DailyDCRStatus)
class DailyDCRStatusAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'date', 'day_type', 'is_open', 'is_submitted', 'is_admin_unlocked', 'unlocked_until')
    list_editable = ('is_open', 'is_admin_unlocked')
    ordering = ('-date', 'employee')

@admin.register(DoctorChemistProductMapping)
class DoctorChemistProductMappingAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('doctor', 'chemist', 'product')

@admin.register(PharmaActivity)
class PharmaActivityAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('title', 'employee', 'doctor', 'status')

class FreeQtyClaimLineInline(admin.TabularInline):
    model = FreeQtyClaimLine
    extra = 0
    readonly_fields = ('product', 'total_billed_qty', 'total_free_qty', 'claim_value')

@admin.register(FreeQtyClaimMaster)
class FreeQtyClaimMasterAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('employee', 'stockist', 'month', 'year', 'status', 'created_at')
    inlines = [FreeQtyClaimLineInline]

@admin.register(DoctorEditRequest)
class DoctorEditRequestAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('doctor', 'req_name', 'employee', 'status', 'created_at')

@admin.register(ChemistEditRequest)
class ChemistEditRequestAdmin(TenantIsolationMixin, admin.ModelAdmin):
    list_display = ('chemist', 'req_name', 'employee', 'status', 'created_at')
    
# ==============================================================================
# 🌟 ACTIVITY & COMMUNITY HUB ADMIN
# ==============================================================================
from .models import FieldEvent, EventPhoto, EventLike, EventComment

class EventPhotoInline(admin.TabularInline):
    model = EventPhoto
    extra = 1  # Event ke andar hi photo upload/dekhne ka option mil jayega
    readonly_fields = ('photo_preview',)

    # 🌟 DEBUG FIX: Actual saved image yahan dikhegi (agar Cloudinary URL
    # broken hai toh ye <img> bhi broken dikhega — turant pata chal jayega)
    def photo_preview(self, obj):
        from django.utils.html import format_html
        if obj.photo:
            return format_html('<img src="{}" style="max-height:80px;" />', obj.photo.url)
        return "(no file)"
    photo_preview.short_description = "Preview"

@admin.register(FieldEvent)
class FieldEventAdmin(admin.ModelAdmin):
    list_display = ('subject', 'employee', 'category', 'event_date', 'is_shared_in_community')
    list_filter = ('category', 'is_shared_in_community', 'event_date', 'territory')
    search_fields = ('subject', 'employee__name', 'description')
    inlines = [EventPhotoInline] # Event ke page par hi uski photos dikhengi
    list_editable = ('is_shared_in_community',) # Admin direct bahar se hi post ko hide/show kar payega

    # 🌟 NAYA: Event delete karte waqt uske saare related records
    # (photos + Cloudinary files, likes, comments) automatically CASCADE se
    # delete ho jaate hain (models.py me on_delete=CASCADE already set hai,
    # aur EventPhoto ke liye ek post_delete signal Cloudinary file bhi
    # delete karta hai). Ye overrides sirf ek confirmation message dikhate
    # hain ki kitna data saath me delete hua — safety/visibility ke liye.
    def delete_model(self, request, obj):
        photos, likes, comments = obj.photos.count(), obj.likes.count(), obj.comments.count()
        super().delete_model(request, obj)
        self.message_user(
            request,
            f"✅ Event delete ho gaya, saath me {photos} photo(s) [Cloudinary se bhi], "
            f"{likes} like(s), {comments} comment(s) bhi delete ho gaye.",
            messages.SUCCESS
        )

    def delete_queryset(self, request, queryset):
        total_photos = sum(obj.photos.count() for obj in queryset)
        total_likes = sum(obj.likes.count() for obj in queryset)
        total_comments = sum(obj.comments.count() for obj in queryset)
        count = queryset.count()
        super().delete_queryset(request, queryset)
        self.message_user(
            request,
            f"✅ {count} event(s) delete ho gaye, saath me {total_photos} photo(s) [Cloudinary se bhi], "
            f"{total_likes} like(s), {total_comments} comment(s) bhi delete ho gaye.",
            messages.SUCCESS
        )

@admin.register(EventPhoto)
class EventPhotoAdmin(admin.ModelAdmin):
    # 🌟 DEBUG FIX: Standalone list jisme har photo ka raw saved path/URL
    # text me dikhega — bina shell ke confirm ho jayega Cloudinary pe gayi ya nahi
    list_display = ('event', 'photo', 'uploaded_at')
    search_fields = ('event__subject',)
    list_filter = ('uploaded_at',)

@admin.register(EventLike)
class EventLikeAdmin(admin.ModelAdmin):
    list_display = ('event', 'employee', 'created_at')
    search_fields = ('event__subject', 'employee__name')
    list_filter = ('created_at',)

@admin.register(EventComment)
class EventCommentAdmin(admin.ModelAdmin):
    list_display = ('event', 'employee', 'comment', 'created_at')
    search_fields = ('event__subject', 'employee__name', 'comment')
    list_filter = ('created_at',)
