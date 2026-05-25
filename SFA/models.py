from django.db import models
from django.contrib.auth.models import User

# ==========================================
# 1. MASTER TABLES (Core Data)
# ==========================================

class Territory(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.name} - {self.city}"
class Route(models.Model):
    name = models.CharField(max_length=150)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} ({self.territory.name})"

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    DESIGNATION_CHOICES = [
        ('MR', 'Medical Representative'),
        ('ABM', 'Area Business Manager'),
        ('RBM', 'Regional Business Manager'),
        ('ZBM', 'Zonal Business Manager'),
        ('NSM', 'National Sales Manager'),
    ]

    name = models.CharField(max_length=100)
    employee_code = models.CharField(max_length=50, unique=True)
    designation = models.CharField(max_length=5, choices=DESIGNATION_CHOICES, default='MR')
    
    # Self-referencing ForeignKey for hierarchy (Manager)
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    
    headquarter = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15)

    def __str__(self):
        return f"{self.name} ({self.designation})"

class Stockist(models.Model):
    name = models.CharField(max_length=150)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)

    def __str__(self):
        return self.name

class Chemist(models.Model):
    name = models.CharField(max_length=150)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    route = models.ForeignKey('Route', on_delete=models.SET_NULL, null=True, blank=True) 
    linked_stockist = models.ForeignKey(Stockist, on_delete=models.SET_NULL, null=True, blank=True) 
    phone = models.CharField(max_length=15)
    allocated_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, help_text="Kis MR ka chemist hai?")
    

    def __str__(self):
        return self.name

class Doctor(models.Model):
    name = models.CharField(max_length=150)
    specialty = models.CharField(max_length=100)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    route = models.ForeignKey('Route', on_delete=models.SET_NULL, null=True, blank=True) 
    allocated_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, help_text="Kis MR ka doctor hai?")
    
    
    def __str__(self):
        return f"Dr. {self.name} ({self.specialty})"

class Product(models.Model):
    name = models.CharField(max_length=150)
    pack_size = models.CharField(max_length=50) 
    price = models.DecimalField(max_digits=10, decimal_places=2) 

    def __str__(self):
        return f"{self.name} ({self.pack_size})"


# ==========================================
# 2. TRANSACTION TABLES (Sales & Reports)
# ==========================================

class PrimarySale(models.Model):
    date = models.DateField()
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(help_text="Number of boxes/units dispatched")
    batch_number = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.stockist.name} - {self.product.name} ({self.date})"

class SecondarySale(models.Model):
    date = models.DateField()
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE) # Changed mr to employee
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    chemist = models.ForeignKey(Chemist, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(help_text="Units ordered by Chemist")

    def __str__(self):
        return f"{self.chemist.name} - {self.product.name} ({self.date})"

class RCPA_Audit(models.Model):
    date = models.DateField()
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE) # Changed mr to employee
    chemist = models.ForeignKey(Chemist, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_prescribed = models.PositiveIntegerField(help_text="Units sold via Doctor's prescription")

    def __str__(self):
        return f"Dr. {self.doctor.name} -> {self.product.name} via {self.chemist.name}"

# ==========================================
# TOUR PROGRAM (MASTER & DETAIL)
# ==========================================

class MonthlyTourProgram(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    month = models.IntegerField(help_text="1 to 12 (e.g., 5 for May)")
    year = models.IntegerField(help_text="e.g., 2026")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ek MR ek mahine ka sirf ek hi MTP bana sakta hai
        unique_together = ('employee', 'month', 'year')

    def __str__(self):
        return f"{self.employee.name} | {self.month}/{self.year} ({self.status})"


class DailyTourPlan(models.Model):
    # Yeh model MTP master se juda hua hai (Master-Detail relationship)
    mtp = models.ForeignKey(MonthlyTourProgram, on_delete=models.CASCADE, related_name='daily_plans')
    date = models.DateField()
    route = models.ForeignKey(Route, on_delete=models.CASCADE)

    class Meta:
        # Ek MTP ke andar ek date ek hi baar aayegi
        unique_together = ('mtp', 'date')

    def __str__(self):
        return f"{self.date} - {self.route.name}"

# ==========================================
# DCR (MASTER & DETAIL)
# ==========================================

# 1. MASTER TABLE (Ek din mein sirf ek banega)
class DailyDCR(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"{self.employee.name} | {self.date}"

# 2. DETAIL TABLE (Iske andar saare Doctors aur Chemists aayenge, jinhe delete bhi kiya ja sakega)
class DCRVisit(models.Model):
    daily_dcr = models.ForeignKey(DailyDCR, on_delete=models.CASCADE, related_name='visits')
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    chemist = models.ForeignKey(Chemist, on_delete=models.SET_NULL, null=True, blank=True)
    remark = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        target = self.doctor.name if self.doctor else (self.chemist.name if self.chemist else "Unknown")
        return f"Visit: {target} on {self.daily_dcr.date}"

# 3. PRODUCT DETAIL (Samples aur Orders)
class DCRProductDetail(models.Model):
    visit = models.ForeignKey(DCRVisit, on_delete=models.CASCADE, related_name='product_details')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    is_detailed = models.BooleanField(default=False)
    sample_qty = models.IntegerField(default=0)
    order_qty = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} (S:{self.sample_qty}, O:{self.order_qty})"


class DayEnd(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    is_closed = models.BooleanField(default=True) # Day end dabate hi True ho jayega
    closed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"{self.employee.name} | {self.date} | Day Closed"
class DayStart(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    
    # YEH NAYA FIELD ADD KARNA HAI:
    routes = models.ManyToManyField(Route, blank=True, help_text="Planned and Extra Routes for the day")
    
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"{self.employee.name} | {self.date} | {self.territory.name}"
