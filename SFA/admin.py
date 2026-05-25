from django.contrib import admin
from .models import (
    Territory, Employee, Stockist, Chemist, Doctor, Product, 
    PrimarySale, SecondarySale, RCPA_Audit, Route, 
    MonthlyTourProgram, DailyTourPlan, # Naye MTP models
    DCR, DCRProductDetail, DayEnd, DayStart
)

# Master Tables
@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory')
    list_filter = ('territory',)

@admin.register(Territory)
class TerritoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'city')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee_code', 'designation', 'manager', 'headquarter', 'phone')
    list_filter = ('designation', 'headquarter')
    search_fields = ('name', 'employee_code')

@admin.register(Stockist)
class StockistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory', 'contact_person', 'phone')

@admin.register(Chemist)
class ChemistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory', 'route', 'linked_stockist', 'allocated_to')
    list_filter = ('territory', 'route', 'allocated_to')

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialty', 'territory', 'route', 'allocated_to')
    list_filter = ('territory', 'route', 'allocated_to')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'pack_size', 'price')


# Transaction Tables
@admin.register(PrimarySale)
class PrimarySaleAdmin(admin.ModelAdmin):
    list_display = ('date', 'stockist', 'product', 'quantity', 'batch_number')
    list_filter = ('date', 'stockist')

@admin.register(SecondarySale)
class SecondarySaleAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'chemist', 'product', 'quantity')
    list_filter = ('date', 'employee')

@admin.register(RCPA_Audit)
class RCPA_AuditAdmin(admin.ModelAdmin):
    list_display = ('date', 'employee', 'doctor', 'product', 'quantity_prescribed')
    list_filter = ('date', 'doctor', 'employee')


# ==========================================
# TOUR PROGRAM (Master & Detail Admin)
# ==========================================

class DailyTourPlanInline(admin.TabularInline):
    model = DailyTourPlan
    extra = 1

@admin.register(MonthlyTourProgram)
class MonthlyTourProgramAdmin(admin.ModelAdmin):
    list_display = ('employee', 'month', 'year', 'status')
    list_filter = ('status', 'month', 'year', 'employee')
    list_editable = ('status',) # Boss yahin se seedha status change kar payega
    inlines = [DailyTourPlanInline] # MTP ke andar hi us mahine ke saare routes dikhenge


# ==========================================
# DCR & DAY TRACKING
# ==========================================

class DCRProductDetailInline(admin.TabularInline):
    model = DCRProductDetail
    extra = 1

@admin.register(DCR)
class DCRAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'route', 'doctor', 'chemist')
    list_filter = ('date', 'employee', 'route')
    inlines = [DCRProductDetailInline] 

@admin.register(DayEnd)
class DayEndAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_closed', 'closed_at')
    list_filter = ('date', 'employee', 'is_closed')

admin.site.register(DayStart)
