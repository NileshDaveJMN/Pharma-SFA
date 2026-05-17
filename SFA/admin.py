from django.contrib import admin
from .models import Territory, Employee, Stockist, Chemist, Doctor, Product, PrimarySale, SecondarySale, RCPA_Audit, Route, TourProgram

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
    # Ab Admin panel mein Manager bhi dikhega
    list_display = ('name', 'employee_code', 'designation', 'manager', 'headquarter', 'phone')
    list_filter = ('designation', 'headquarter')
    search_fields = ('name', 'employee_code')

@admin.register(Stockist)
class StockistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory', 'contact_person', 'phone')

@admin.register(Chemist)
class ChemistAdmin(admin.ModelAdmin):
    list_display = ('name', 'territory', 'route', 'linked_stockist', 'allocated_to') # route add kiya
    list_filter = ('territory', 'route', 'allocated_to')
@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialty', 'territory', 'route', 'allocated_to') # route add kiya
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

@admin.register(TourProgram)
class TourProgramAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'route', 'status')
    list_filter = ('status', 'date', 'employee')
    list_editable = ('status',) # Boss yahin se seedha status change kar payega
    date_hierarchy = 'date'
    
# SFA/admin.py ke sabse upar imports mein naye models add karein
from .models import Territory, Route, Stockist, Employee, Chemist, Doctor, Product, PrimarySale, SecondarySale, TourProgram, DCR, DCRProductDetail, DayEnd

# Ek visit ke andar hi saare products dikhane ke liye Inline classes use karenge
class DCRProductDetailInline(admin.TabularInline):
    model = DCRProductDetail
    extra = 1

@admin.register(DCR)
class DCRAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'route', 'doctor', 'chemist')
    list_filter = ('date', 'employee', 'route')
    inlines = [DCRProductDetailInline] # Isse visit ke andar hi products ka table dikhega

@admin.register(DayEnd)
class DayEndAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_closed', 'closed_at')
    list_filter = ('date', 'employee', 'is_closed')
