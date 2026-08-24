from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys

class Company(models.Model):
    PLAN_CHOICES = [('trial', 'Trial'), ('basic', 'Basic'), ('pro', 'Pro')]
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    financial_year_start = models.PositiveSmallIntegerField(default=4)
    currency = models.CharField(max_length=10, default='INR')
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    subscription_plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='trial')
    subscription_expiry = models.DateField(null=True, blank=True)
    max_users = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"{self.name} ({self.code})"

class Territory(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='territories') # 🌟 CHANGED
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    
    class Meta:
        # 🌟 NAYA: SaaS Fix - Har company ka apna unique territory naam ho sakta hai
        unique_together = ('company', 'name')

    def __str__(self): return f"{self.name} - {self.city}"

class Route(models.Model):
    STATUS_CHOICES = (('Pending', 'Pending Approval'), ('Approved', 'Approved'), ('Rejected', 'Rejected'))
    CATEGORY_CHOICES = [
        ('HQ', 'Headquarter'),
        ('EX_HQ', 'Ex-Headquarter'),
        ('OUTSTATION', 'Outstation'),
    ]
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='routes') # 🌟 CHANGED
    name = models.CharField(max_length=150)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='HQ')
    distance_from_hq = models.DecimalField(max_digits=6, decimal_places=1, default=0.0, help_text="Distance in KM from HQ")
    requested_by = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='requested_routes')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    class Meta:
        # 🌟 NAYA: SaaS Fix - Ek territory me route name unique hoga
        unique_together = ('territory', 'name')

    def save(self, *args, **kwargs):
        # 🌟 FIX: Agar company explicitly pass nahi hui, toh territory se utha lo
        if not self.company_id and self.territory_id:
            self.company = self.territory.company
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.name} ({self.territory.name}) [{self.category}] - {self.distance_from_hq} km"

class Employee(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='employees') # Already Correct
    DESIGNATION_CHOICES = [
        ('MR', 'Medical Representative'),
        ('ABM', 'Area Business Manager'),
        ('RBM', 'Regional Business Manager'),
        ('ZBM', 'Zonal Business Manager'),
        ('NSM', 'National Sales Manager'),
        ('Admin', 'System Administrator'),
    ]
    name = models.CharField(max_length=100)
    employee_code = models.CharField(max_length=50) # 🌟 FIX: unique=True HATA DIYA HAI
    designation = models.CharField(max_length=5, choices=DESIGNATION_CHOICES, default='MR')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    headquarter = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15)
    joining_date = models.DateField(default=timezone.now, help_text="Employee ki company join karne ki date. DCR calendar is date se aage hi banega, pehle ka nahi.")
    
    # 🌟 NAYE FIELDS (Profile aur Resignation Handle Karne Ke Liye)
    photo = models.ImageField(upload_to='employee_photos/', blank=True, null=True, help_text="Employee ki profile photo")
    address = models.TextField(blank=True, null=True, help_text="Employee ka home address")
    is_active = models.BooleanField(default=True, help_text="False matlab ye employee company chhod chuka hai ya inactive hai.")
    leaving_date = models.DateField(null=True, blank=True, help_text="Employee ke company chhodne ki tareekh.")
    # 🌟 NAYA: Personal & Family Info
    dob = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    anniversary = models.DateField(null=True, blank=True, verbose_name="Marriage Anniversary")
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    emergency_contact = models.CharField(max_length=15, blank=True, null=True)
    permanent_address = models.TextField(blank=True, null=True)
    
    # Family Info
    father_name = models.CharField(max_length=100, blank=True, null=True)
    father_dob = models.DateField(null=True, blank=True)
    father_mobile = models.CharField(max_length=15, blank=True, null=True)
    father_occupation = models.CharField(max_length=100, blank=True, null=True)
    
    mother_name = models.CharField(max_length=100, blank=True, null=True)
    mother_dob = models.DateField(null=True, blank=True)
    mother_mobile = models.CharField(max_length=15, blank=True, null=True)
    mother_occupation = models.CharField(max_length=100, blank=True, null=True)
    
    spouse_name = models.CharField(max_length=100, blank=True, null=True)
    spouse_dob = models.DateField(null=True, blank=True)
    spouse_mobile = models.CharField(max_length=15, blank=True, null=True)
    spouse_occupation = models.CharField(max_length=100, blank=True, null=True)
    
    child1_name = models.CharField(max_length=100, blank=True, null=True)
    child1_dob = models.DateField(null=True, blank=True)
    child2_name = models.CharField(max_length=100, blank=True, null=True)
    child2_dob = models.DateField(null=True, blank=True)
    EMPLOYMENT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('resigned', 'Resigned'),
        ('retired', 'Retired'),
        ('transferred', 'Transferred'),
        ('terminated', 'Terminated'),
        ('vacant', 'Vacant (Placeholder)'),   # 🌟 Dummy employee jab tak naya MR na aaye
        ('archived', 'Archived (Old Dummy)'), # 🌟 Dummy jiska kaam ho gaya, naye employee ko sab de diya
    ]
    employment_status = models.CharField(
        max_length=15, choices=EMPLOYMENT_STATUS_CHOICES, default='active',
        help_text="is_active sirf access/login control karta hai; ye field WAJAH/reason batata hai."
    )
    is_placeholder = models.BooleanField(
        default=False,
        help_text="True = ye ek 'Vacant_<HQ>' dummy employee hai, asli insaan nahi. Joint Work me normal employee jaisa hi treat hota hai (use individual hi maana jayega)."
    )

    class Meta:
        # 🌟 NAYA: SaaS Fix - Har company ka employee code waha unique hona chahiye
        unique_together = ('company', 'employee_code')

    def __str__(self):
        # Inactive employees ke naam ke aage (Inactive) dikhayega
        status = "" if self.is_active else " (Inactive)"
        return f"{self.name} ({self.designation}){status}"

    def get_my_managers(self, include_inactive=False):
        # 🌟 FIX: Resigned (is_active=False) manager joint-work dropdown
        # jaisi jagah par na dikhe, isliye default mein skip karte hain.
        managers = []
        boss = self.manager
        while boss is not None:
            if include_inactive or boss.is_active:
                managers.append(boss)
            boss = boss.manager
        return managers

    def clean(self):
        # 🔒 Manager hierarchy me circular loop check (A->B->C->A jaisa)
        if self.manager_id is not None:
            if self.manager_id == self.id:
                raise ValidationError({'manager': "Employee apna khud ka manager nahi ban sakta."})

            seen_ids = {self.id} if self.id else set()
            boss = self.manager
            while boss is not None:
                if boss.id in seen_ids:
                    raise ValidationError({'manager': f"Ye manager assign nahi ho sakta — isse hierarchy me circular loop ban jayega ({boss.name} se hote hue wapas yahi tak)."})
                seen_ids.add(boss.id)
                boss = boss.manager

class DARate(models.Model):
    DESIGNATION_CHOICES = [
        ('MR', 'Medical Representative'),
        ('ABM', 'Area Business Manager'),
        ('RBM', 'Regional Business Manager'),
        ('ZBM', 'Zonal Business Manager'),
        ('NSM', 'National Sales Manager'),
        ('Admin', 'System Administrator'),
    ]
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="da_rates") # 🌟 CHANGED
    designation   = models.CharField(max_length=5, choices=DESIGNATION_CHOICES) # 🌟 FIX: unique=True HATA DIYA HAI
    hq_da         = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    exhq_da       = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    outstation_da = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    class Meta:
        # 🌟 NAYA: SaaS Fix
        unique_together = ('company', 'designation')

    def __str__(self): return f"{self.designation} — HQ:{self.hq_da} | ExHQ:{self.exhq_da} | OS:{self.outstation_da}"

class TARate(models.Model):
    DESIGNATION_CHOICES = [
        ('MR', 'Medical Representative'),
        ('ABM', 'Area Business Manager'),
        ('RBM', 'Regional Business Manager'),
        ('ZBM', 'Zonal Business Manager'),
        ('NSM', 'National Sales Manager'),
        ('Admin', 'System Administrator'),
    ]
    company       = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="ta_rates") # 🌟 CHANGED
    designation   = models.CharField(max_length=5, choices=DESIGNATION_CHOICES) # 🌟 FIX: unique=True HATA DIYA HAI
    # Slab 1: 1 to slab1_upto_km
    slab1_upto_km = models.IntegerField(default=100, help_text="Slab 1 upper limit (km)")
    slab1_rate    = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="₹/km for Slab 1")
    # Slab 2: slab1+1 to slab2_upto_km
    slab2_upto_km = models.IntegerField(default=200, help_text="Slab 2 upper limit (km)")
    slab2_rate    = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, help_text="₹/km for Slab 2")
    
    class Meta:
        # 🌟 NAYA: SaaS Fix
        unique_together = ('company', 'designation')
    
    # Slab 3: above slab2 → Actual fare input by MR (Option C)
    # No rate stored — actual_fare field in DailyExpense
    def __str__(self): return f"{self.designation} — Slab1:{self.slab1_rate}/km (≤{self.slab1_upto_km}km) | Slab2:{self.slab2_rate}/km (≤{self.slab2_upto_km}km) | 200+:Actual"

class Stockist(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stockists') # 🌟 CHANGED
    name = models.CharField(max_length=150)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)

    def save(self, *args, **kwargs):
        # 🌟 FIX: Agar company explicitly pass nahi hui, toh territory se utha lo
        if not self.company_id and self.territory_id:
            self.company = self.territory.company
        super().save(*args, **kwargs)

    def __str__(self): return self.name

class Doctor(models.Model):
    STATUS_CHOICES   = (('Pending', 'Pending Approval'), ('Approved', 'Approved'), ('Rejected', 'Rejected'))
    CATEGORY_CHOICES = (('A', 'Category A'), ('B', 'Category B'), ('C', 'Category C'))
    
    # 🌟 NAYA LOGIC: Fixed Choices for Specialty and Degree
    SPECIALTY_CHOICES = [
        ('GP', 'General Physician (GP)'),
        ('Gynecologist', 'Gynecologist (OB/GYN)'),
        ('Pediatrician', 'Pediatrician (Child Specialist)'),
        ('Orthopedic', 'Orthopedic (Bone Specialist)'),
        ('Cardiologist', 'Cardiologist (Heart Specialist)'),
        ('Dermatologist', 'Dermatologist (Skin Specialist)'),
        ('Dentist', 'Dentist / Dental Surgeon'),
        ('Surgeon', 'General Surgeon'),
        ('ENT', 'ENT Specialist'),
        ('Psychiatrist', 'Psychiatrist'),
        ('Ophthalmologist', 'Ophthalmologist (Eye Specialist)'),
        ('Physician', 'Consultant Physician'),
        ('Other', 'Other')
    ]

    DEGREE_CHOICES = [
        ('MBBS', 'MBBS'),
        ('MD', 'MD'),
        ('MS', 'MS'),
        ('BAMS', 'BAMS'),
        ('BHMS', 'BHMS'),
        ('BDS', 'BDS'),
        ('MDS', 'MDS'),
        ('DM', 'DM'),
        ('MCh', 'MCh'),
        ('Diploma', 'Diploma (DGO, DCH, etc.)'),
        ('Other', 'Other')
    ]

    # Core fields (existing)
    company      = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='doctors') # 🌟 CHANGED
    name         = models.CharField(max_length=150)
    specialty    = models.CharField(max_length=100, choices=SPECIALTY_CHOICES, blank=True, null=True) # 🌟 Updated
    territory    = models.ForeignKey(Territory, on_delete=models.CASCADE)
    route        = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)
    allocated_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    # New fields
    address      = models.TextField(blank=True, null=True)
    residential_address = models.TextField(blank=True, null=True, verbose_name="Residential Address")  # 🌟 NAYA
    mobile       = models.CharField(max_length=15, blank=True, null=True)
    email        = models.EmailField(blank=True, null=True)
    degree       = models.CharField(max_length=100, choices=DEGREE_CHOICES, blank=True, null=True) # 🌟 Updated
    category     = models.CharField(max_length=1, choices=CATEGORY_CHOICES, blank=True, null=True)
    dob          = models.DateField(blank=True, null=True, verbose_name="Date of Birth")
    dom          = models.DateField(blank=True, null=True, verbose_name="Date of Marriage")
    spouse_dob   = models.DateField(blank=True, null=True, verbose_name="Spouse Date of Birth")
    child_1_dob  = models.DateField(blank=True, null=True, verbose_name="Child 1 Date of Birth")  # 🌟 NAYA
    child_2_dob  = models.DateField(blank=True, null=True, verbose_name="Child 2 Date of Birth")  # 🌟 NAYA
    photo        = models.ImageField(upload_to='doctors/photos/', blank=True, null=True)
    vcard_photo  = models.ImageField(upload_to='doctors/vcards/', blank=True, null=True)
    latitude     = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    def save(self, *args, **kwargs):
        # 🌟 FIX: Agar company explicitly pass nahi hui, toh territory (ya fallback allocated_to) se utha lo
        if not self.company_id:
            if self.territory_id:
                self.company = self.territory.company
            elif self.allocated_to_id:
                self.company = self.allocated_to.company
        super().save(*args, **kwargs)

    def __str__(self): 
        return f"Dr. {self.name} ({self.get_specialty_display() if self.specialty else 'N/A'}) - {self.status}"


class Chemist(models.Model):
    STATUS_CHOICES = (('Pending', 'Pending Approval'), ('Approved', 'Approved'), ('Rejected', 'Rejected'))
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='chemists')
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True, null=True, help_text="Chemist shop address")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE)
    route = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)
    linked_stockist = models.ForeignKey(Stockist, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15)
    allocated_to = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    # 🌟 NAYA: Owner Info & Card Photo
    owner_name = models.CharField(max_length=150, blank=True, null=True, help_text="Chemist shop owner ka naam")
    owner_dob = models.DateField(blank=True, null=True, help_text="Owner ki date of birth")
    card_photo = models.ImageField(upload_to='chemist_cards/', blank=True, null=True, help_text="Chemist ki visiting card ki photo")

    def save(self, *args, **kwargs):
        if not self.company_id:
            if self.territory_id:
                self.company = self.territory.company
            elif self.allocated_to_id:
                self.company = self.allocated_to.company
        super().save(*args, **kwargs)

    def __str__(self): 
        return f"{self.name} ({self.status})"

class Product(models.Model):
    GST_SLAB_CHOICES = [
        (0, '0%'),
        (5, '5%'),
        (12, '12%'),
        (18, '18%'),
        (28, '28%'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='products') # 🌟 CHANGED
    name = models.CharField(max_length=150)
    pack_size = models.CharField(max_length=50)

    # 🌟 NAYE FIELDS — pehle sirf ek hi 'price' tha
    mrp = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ptr = models.DecimalField(max_digits=10, decimal_places=2, default=0)   # Price to Retailer
    pts = models.DecimalField(max_digits=10, decimal_places=2, default=0)   # Price to Stockist — company ko kitna milta hai
    gst_slab = models.PositiveSmallIntegerField(choices=GST_SLAB_CHOICES, default=12)

    class Meta:
        # 🌟 NAYA: SaaS Fix
        unique_together = ('company', 'name')

    def __str__(self):
        return f"{self.name} ({self.pack_size})"

    # 🌟 BACKWARD COMPATIBILITY: Saare purane reports/views 'product.price'
    # use karte hain — ab wo automatically PTS return karega (company revenue
    # basis). Isse ek bhi report file change nahi karni padi.
    # Baad mein jab PTR/PTS toggle banayenge, tab har report mein ye property
    # ki jagah get_product_value(product, basis) helper use karenge.
    @property
    def price(self):
        return self.pts

class PrimarySale(models.Model):
    date = models.DateField()
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    free_quantity = models.PositiveIntegerField(default=0)  # 🌟 NAYA: Company scheme/CN se mili free qty. Agar company nahi deti, 0 hi rahega.
    batch_number = models.CharField(max_length=50)
    def __str__(self):
        return f"{self.product.name} ({self.quantity}+{self.free_quantity} free) - {self.stockist.name}"

class SecondarySale(models.Model):
    date = models.DateField()
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    chemist = models.ForeignKey(Chemist, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

class RCPA_Audit(models.Model):
    date = models.DateField()
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    chemist = models.ForeignKey(Chemist, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_prescribed = models.PositiveIntegerField()

class MonthlyTourProgram(models.Model):
    STATUS_CHOICES = (('Draft', 'Draft'), ('Pending', 'Pending Approval'), ('Approved', 'Approved'), ('Rejected', 'Rejected'))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    month = models.IntegerField()
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    manager_remark = models.TextField(blank=True, null=True)
    is_modified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ('employee', 'month', 'year')
    def __str__(self): return f"{self.employee.name} | {self.month}/{self.year}"

class DailyTourPlan(models.Model):
    mtp = models.ForeignKey(MonthlyTourProgram, on_delete=models.CASCADE, related_name='daily_plans')
    date = models.DateField()
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    class Meta: unique_together = ('mtp', 'date')

class DailyDCR(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ('employee', 'date')
    def __str__(self): return f"{self.employee.name} | {self.date}"

# ==============================================================================
# 📅 SMART DCR CALENDAR (JIT TRACKING)
# ==============================================================================
class DailyDCRStatus(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    
    is_open = models.BooleanField(default=True, help_text="Kya is din ka DCR bharna allowed hai?")
    is_submitted = models.BooleanField(default=False, help_text="Day End hone par True ho jayega")
    is_admin_unlocked = models.BooleanField(default=False, help_text="Admin Override (True karne par 1 din ke liye auto-block bypass ho bypass ho jayega)")
    unlocked_until = models.DateField(null=True, blank=True, help_text="Is date tak unlock valid hai. Iske baad khud-ba-khud wapas lock ho jayega. (Khud bhar na karein, save par auto-set hota hai)")
    
    day_type = models.CharField(max_length=20, default='Working') # Working, Holiday, Sunday, Leave

    class Meta:
        unique_together = ('employee', 'date')
        verbose_name_plural = "Daily DCR Statuses"

    def __str__(self):
        return f"{self.employee.name} | {self.date} | Open: {self.is_open}"

    def save(self, *args, **kwargs):
        # 🔓 Jab Admin naya unlock tick kare, validity sirf AAJ ke din tak set hogi
        # AUR is din ko actually 'open' bhi karna hai (agar already submit nahi hua)
        if self.is_admin_unlocked and not self.unlocked_until:
            self.unlocked_until = timezone.now().date()
            if not self.is_submitted:
                self.is_open = True
        # Agar unlock unticked hai, to validity bhi clear kar do
        if not self.is_admin_unlocked:
            self.unlocked_until = None
        super().save(*args, **kwargs)

class DCRVisit(models.Model):
    daily_dcr = models.ForeignKey(DailyDCR, on_delete=models.CASCADE, related_name='visits')
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    chemist = models.ForeignKey(Chemist, on_delete=models.SET_NULL, null=True, blank=True)
    remark = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    geofence_bypassed = models.BooleanField(
        default=False,
        help_text="True if backdated entry is made without location punch"
        )

class DCRProductDetail(models.Model):
    visit = models.ForeignKey(DCRVisit, on_delete=models.CASCADE, related_name='product_details')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    is_detailed = models.BooleanField(default=False)
    sample_qty = models.IntegerField(default=0)
    order_qty = models.IntegerField(default=0)

class DayEnd(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    is_closed = models.BooleanField(default=True)
    closed_at = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    class Meta: unique_together = ('employee', 'date')

class DayStart(models.Model):
    WORK_TYPE_CHOICES = [
        ('Field Work', 'Field Work'),
        ('Meeting', 'Meeting'),
        ('Transit', 'Transit'),
        ('Strike', 'Strike'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE, null=True, blank=True)
    routes = models.ManyToManyField(Route, blank=True)
    night_stay = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    
    # 🌟 NAYE FIELDS FOR ANALYSIS HUB
    work_type = models.CharField(max_length=20, choices=WORK_TYPE_CHOICES, default='Field Work')
    joint_worked_with = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='joint_days')

    class Meta: 
        unique_together = ('employee', 'date')


class MonthlyExpenseReport(models.Model):
    STATUS_CHOICES = (('Draft', 'Draft'), ('Pending', 'Pending Approval'), ('Approved', 'Approved'), ('Rejected', 'Rejected'))
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='monthly_expenses')
    month = models.IntegerField()
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    manager_remark = models.TextField(blank=True, null=True)
    is_modified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ('employee', 'month', 'year')

class DailyExpense(models.Model):
    TERRITORY_CATEGORY_CHOICES = [
        ('HQ', 'Headquarter'),
        ('EX_HQ', 'Ex-Headquarter'),
        ('OUTSTATION', 'Outstation'),
        ('RETURN', 'Return Day'),
    ]
    monthly_report = models.ForeignKey(MonthlyExpenseReport, on_delete=models.CASCADE, related_name='daily_lines', null=True, blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField()
    territory_category = models.CharField(max_length=15, choices=TERRITORY_CATEGORY_CHOICES, blank=True, null=True)
    night_stay = models.BooleanField(default=False)
    distance_km = models.DecimalField(max_digits=6, decimal_places=1, default=0.0)
    
    ta_amount    = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    da_amount    = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    misc_amount  = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    # 🌟 NAYA FIELD: Misc Bill Photo upload karne ke liye
    misc_bill    = models.ImageField(upload_to='expense_bills/', blank=True, null=True, help_text="Bill photo for miscellaneous expense")
    
    # Slab 3 (200+ km): MR actual fare manually enter karta hai
    actual_fare  = models.DecimalField(max_digits=8, decimal_places=2, default=0.00,
                    help_text="200+ km pe actual travel fare — MR enters at Day End")
    is_slab3     = models.BooleanField(default=False, help_text="True if distance > slab2_upto_km")
    
    approved_ta   = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    approved_da   = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    approved_misc = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    remark = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta: 
        unique_together = ('employee', 'date')


class StockistProductStatement(models.Model):
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE, related_name='statements')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='stockist_statements')
    month = models.IntegerField()
    year = models.IntegerField()
    opening_qty = models.IntegerField(default=0)
    received_qty = models.IntegerField(default=0)
    sale_qty = models.IntegerField(default=0)
    class Meta: unique_together = ('stockist', 'product', 'month', 'year')
    def __str__(self): return f"{self.stockist.name} - {self.product.name} ({self.month}/{self.year})"

class DoctorChemistProductMapping(models.Model):
    doctor = models.ForeignKey('Doctor', on_delete=models.CASCADE, related_name='doc_mappings')
    chemist = models.ForeignKey('Chemist', on_delete=models.CASCADE, related_name='chem_mappings')
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    class Meta:
        unique_together = ('doctor', 'chemist', 'product')
    def __str__(self):
        return f"Dr. {self.doctor.name} ➔ {self.chemist.name} ({self.product.name})"

class PharmaActivity(models.Model):
    STATUS_CHOICES = (
        ('Pending_Manager', 'Pending Manager Approval'),
        ('Pending_Admin', 'Pending Admin Approval'),
        ('Approved_Live', 'Approved & Running'),
        ('Rejected', 'Rejected')
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='created_activities')
    doctor = models.ForeignKey('Doctor', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending_Manager')
    approved_by_managers = models.JSONField(default=list, blank=True, help_text="List of Manager IDs who approved")
    manager_remark = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.title} | {self.doctor.name} | {self.status}"

# ==============================================================================
# 🏢 NAYA: PARTY-WISE SALE & DOCTOR RX CLASSIFICATION MODELS
# ==============================================================================

class PartyWiseSaleReport(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    month = models.IntegerField()
    year = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'stockist', 'month', 'year')

    def __str__(self):
        return f"Party Wise: {self.stockist.name} - {self.month}/{self.year}"

class PartyWiseSaleLine(models.Model):
    report = models.ForeignKey(PartyWiseSaleReport, related_name='lines', on_delete=models.CASCADE)
    chemist = models.ForeignKey(Chemist, on_delete=models.SET_NULL, null=True, blank=True)     
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    billed_qty = models.IntegerField(default=0) 
    free_qty = models.IntegerField(default=0)

    def __str__(self):
        # Safe checks: Agar chemist/product nahi hai toh crash na ho
        chemist_name = self.chemist.name if self.chemist else "No Chemist"
        product_name = self.product.name if self.product else "No Product"
        return f"{chemist_name} - {product_name} (B:{self.billed_qty}, F:{self.free_qty})"

class DoctorRxMapping(models.Model):
    party_line = models.ForeignKey(PartyWiseSaleLine, related_name='dr_mappings', on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    mapped_billed_qty = models.IntegerField(default=0)
    mapped_free_qty = models.IntegerField(default=0)

    def __str__(self):
        # Safe checks for DoctorRxMapping
        doc_name = self.doctor.name if self.doctor else "No Doctor"
        prod_name = "No Product"
        if self.party_line and self.party_line.product:
            prod_name = self.party_line.product.name
        return f"Dr. {doc_name} -> {prod_name} ({self.mapped_billed_qty})"

class TerritoryTarget(models.Model):
    # 🌟 Employee ki jagah seedha Territory (HQ) laga diya
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE, related_name='targets')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    month = models.IntegerField(help_text="Month in number (e.g., 1 for Jan, 5 for May)")
    year = models.IntegerField()
    target_qty = models.IntegerField(default=0)
    target_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total value of target (Qty * Price)")

    class Meta:
        unique_together = ('territory', 'product', 'month', 'year')
        verbose_name = "HQ / Territory Target"
        verbose_name_plural = "HQ / Territory Targets"

    def __str__(self):
        return f"{self.territory.name} - {self.product.name} ({self.month}/{self.year})"

# ==============================================================================
# 🎯 TARGET APPROVAL MASTER MODEL
# ==============================================================================
class MonthlyTargetMaster(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending_Manager', 'Pending Manager'),
        ('Pending_RSM', 'Pending RSM'),
        ('Pending_ZSM', 'Pending ZSM'),
        ('Pending_Admin', 'Pending Admin'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    
    # 🌟 NAYA: Employee ki jagah seedha Territory (HQ) laga diya
    territory = models.ForeignKey(Territory, on_delete=models.CASCADE, related_name='monthly_target_masters')
    
    month = models.IntegerField(help_text="Month in number (e.g., 1 for Jan, 5 for May)")
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    manager_remark = models.TextField(blank=True, null=True)
    approved_by_managers = models.JSONField(default=list, blank=True)

    class Meta:
        # 🌟 NAYA: Ek HQ ka ek mahine me ek hi master approval banega
        unique_together = ('territory', 'month', 'year')
        verbose_name = "Monthly Target Master"
        verbose_name_plural = "Monthly Target Masters"

    def __str__(self):
        # 🌟 NAYA: Name me ab Employee ki jagah Territory ka naam dikhega
        return f"{self.territory.name} Target - {self.month}/{self.year} ({self.status})"

# ==============================================================================
# 🌴 HOLIDAY MASTER MODEL
# ==============================================================================
class Holiday(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="holidays") # 🌟 CHANGED
    name = models.CharField(max_length=100)
    date = models.DateField()
    proposed_by = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='proposed_holidays')
    status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')], default='Pending')

    class Meta:
        unique_together = ('date', 'proposed_by')

    def save(self, *args, **kwargs):
        # 🌟 FIX: Agar company explicitly pass nahi hui, toh proposed_by (Employee) se utha lo
        if not self.company_id and self.proposed_by_id:
            self.company = self.proposed_by.company
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.date} ({self.status})"
# ==============================================================================
# 🏖️ LEAVE MANAGEMENT SYSTEM
# ==============================================================================

class LeaveBalance(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='leave_balance')
    year = models.IntegerField(default=2026) # Current Year
    
    # Allocated by Admin
    cl_total = models.FloatField(default=0.0, verbose_name="Total CL")
    cl_used = models.FloatField(default=0.0, verbose_name="Used CL")
    
    sl_total = models.FloatField(default=0.0, verbose_name="Total SL")
    sl_used = models.FloatField(default=0.0, verbose_name="Used SL")
    
    pl_total = models.FloatField(default=0.0, verbose_name="Total PL/EL")
    pl_used = models.FloatField(default=0.0, verbose_name="Used PL/EL")

    def __str__(self):
        return f"{self.employee.name} - Leave Balance ({self.year})"

class LeaveApplication(models.Model):
    LEAVE_TYPES = (
        ('CL', 'Casual Leave (CL)'),
        ('SL', 'Sick Leave (SL)'),
        ('PL', 'Privilege/Earned Leave (PL/EL)'),
        ('LWP', 'Leave Without Pay (LWP)')
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    )
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_applications')
    leave_type = models.CharField(max_length=5, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    manager_remark = models.TextField(blank=True, null=True)
    applied_on = models.DateTimeField(auto_now_add=True)

    @property
    def no_of_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.employee.name} | {self.leave_type} | {self.start_date} to {self.end_date}"

# ==============================================================================
# 🛣️ HQ TO HQ DISTANCE (For Manager Joint Working)
# ==============================================================================
class HQDistance(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="hq_distances") # 🌟 CHANGED
    from_territory = models.ForeignKey(Territory, related_name='transit_from', on_delete=models.CASCADE)
    to_territory = models.ForeignKey(Territory, related_name='transit_to', on_delete=models.CASCADE)
    distance_km = models.DecimalField(max_digits=6, decimal_places=1, default=0.0, help_text="Distance between two HQs in KM")

    class Meta:
        unique_together = ('from_territory', 'to_territory')
        verbose_name = "HQ to HQ Distance"
        verbose_name_plural = "HQ to HQ Distances"

    def save(self, *args, **kwargs):
        # 🌟 FIX: Agar company explicitly pass nahi hui, toh from_territory se utha lo
        if not self.company_id and self.from_territory_id:
            self.company = self.from_territory.company
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.from_territory.name} to {self.to_territory.name} : {self.distance_km} km"
# ==============================================================================
# 📢 1. COMPANY NOTICE BOARD (Admin to All)
# ==============================================================================
class CompanyNotice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='notices') # 🌟 CHANGED
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True, help_text="Inactive notices won't show on dashboard")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 🌟 FIX: Purane views abhi bhi `company=` pass nahi karte (sirf created_by dete hain).
        # Isliye har jagah views change karne ke bajaye, yahin se created_by (Employee) ki
        # company automatically utha lete hain — sab .create()/.save() calls yahi se guzarte hain.
        if not self.company_id and self.created_by_id:
            self.company = self.created_by.company
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

# ==============================================================================
# 🔔 2. SYSTEM NOTIFICATIONS (Auto-Pilot Alerts)
# ==============================================================================
class SystemNotification(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Alert for {self.employee.name} - {self.title}"

# ==============================================================================
# 💬 3. DIRECT MESSAGES (Manager <-> MR)
# ==============================================================================
class DirectMessage(models.Model):
    sender = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='received_messages')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"From {self.sender.name} to {self.receiver.name}"
class SystemSetting(models.Model):
    # 🌟 FIX: unique=True add kiya — ab DB khud kabhi bhi ek company ke liye
    # 2 SystemSetting rows nahi banne dega (chahe code me kahin se bhi
    # inconsistent create call ho). Isse pehle ye plain ForeignKey tha,
    # jiski wajah se duplicate rows ban gayi thi aur MultipleObjectsReturned
    # error aa raha tha.
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='settings')
    allow_location_capture = models.BooleanField(
        default=True, 
        help_text="Isko ON rakhne par MRs location update kar payenge. OFF karne par button gayab ho jayega."
    )
    
    # ==========================================
    # 🕒 COMPLIANCE & DEADLINE SETTINGS
    # ==========================================
    dcr_lock_days = models.PositiveIntegerField(default=3, help_text="Pichle kitne din tak ka DCR bharne ki permission hai? (Default: 3)")
    mtp_approval_deadline_day = models.PositiveIntegerField(default=25, help_text="Agale mahine ka Tour Plan submit karne ki aakhiri tareekh (Default: 25th)")
    expense_submit_deadline_day = models.PositiveIntegerField(default=4, help_text="Pichle mahine ka Expense submit karne ki aakhiri tareekh (Default: 4th)")
    sale_upload_deadline_day = models.PositiveIntegerField(default=4, help_text="Pichle mahine ki Secondary Sale/Rx submit karne ki aakhiri tareekh (Default: 4th)")
    free_claim_deadline_day = models.PositiveIntegerField(default=4, help_text="Pichle mahine ka Free Claim generate/submit karne ki aakhiri tareekh (Default: 4th)")
    target_approval_deadline_day = models.PositiveIntegerField(default=4, help_text="Is mahine ka Target approve hone ki aakhiri tareekh (Default: 4th)")
    enable_offline_mode = models.BooleanField(
        default=True, 
        help_text="Enable to allow the app to save data locally and sync when online. Disable to force online-only data submission."
    )

    # ==========================================
    # 🛑 STRICT BLOCKER RULES (True/False)
    # ==========================================
    without_tourplan_dcr_block = models.BooleanField(default=True, help_text="ON (True): Agar MTP submit nahi hai, toh DCR block ho jayega.")
    allow_current_month_mtp = models.BooleanField(default=False, help_text="ON (True): Current month ka MTP bhi add karne dega (deadline ke baad bhi). Testing/exception ke liye.")
    manager_pending_approval_block = models.BooleanField(default=True, help_text="ON (True): Agar Manager ke paas team approvals pending hain, toh Manager ka DCR block hoga.")
    strict_geofence_for_backdate = models.BooleanField(default=False, help_text="OFF (False): Backdate DCR bina location ke bhar sakte hain (Exceptions track honge).")

    class Meta:
        verbose_name_plural = "System Settings"

    def __str__(self):
        return "Global Master Settings"


class FreeQtyClaimMaster(models.Model):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending_Manager', 'Pending Manager Approval'),
        ('Pending_Admin', 'Pending Admin Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    ]
    
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='free_claims')
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE, null=True, blank=True)
    month = models.IntegerField()
    year = models.IntegerField()
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='Draft')
    
    # Approval tracking (Managers ke IDs is list mein save honge)
    approved_by_managers = models.JSONField(default=list, blank=True) 
    manager_remark = models.TextField(blank=True, null=True)
    admin_remark = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 🌟 SMART FIX: Ek mahine ki ek MR ki sirf 1 hi report ban sakti hai
        unique_together = ('employee', 'stockist', 'month', 'year')

    def __str__(self):
        return f"Claim - {self.employee.name} - {self.month}/{self.year}"

class FreeQtyClaimLine(models.Model):
    master = models.ForeignKey(FreeQtyClaimMaster, on_delete=models.CASCADE, related_name='claim_lines')
    stockist = models.ForeignKey('Stockist', on_delete=models.CASCADE)
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    
    total_billed_qty = models.IntegerField(default=0)
    total_free_qty = models.IntegerField(default=0)
    claim_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # (Free Qty * Price)

    def __str__(self):
        return f"{self.stockist.name} - {self.product.name} ({self.total_free_qty} Free)"

# ==========================================
# 🎁 SAMPLE & INPUT MANAGEMENT MODULE
# ==========================================

class PromoItem(models.Model):
    ITEM_TYPES = (
        ('Sample', 'Sample (Medicine)'),
        ('Routine', 'Routine Input (< ₹1000)'),
        ('HighValue', 'High-Value Gift (> ₹1000)')
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='promo_items') # 🌟 CHANGED
    name = models.CharField(max_length=100) # Item ka naam (e.g., "Nsaid Catch Cover" ya "Company Pen")
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES)
    
    # 🌟 NAYA: Main Product se Link kar diya!
    linked_product = models.ForeignKey('Product', on_delete=models.SET_NULL, null=True, blank=True, help_text="Sirf Sample ke liye product select karein")
    
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_item_type_display()})"


class PromoDispatch(models.Model):
    STATUS_CHOICES = (
        ('In-Transit', 'In-Transit'),
        ('Received', 'Received by MR')
    )
    dispatch_date = models.DateField(auto_now_add=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    item = models.ForeignKey(PromoItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='In-Transit')
    received_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.item.name} -> {self.employee.name} ({self.status})"


class MRInventory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    item = models.ForeignKey(PromoItem, on_delete=models.CASCADE)
    stock_qty = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('employee', 'item')

    def __str__(self):
        return f"{self.employee.name} | {self.item.name} | Stock: {self.stock_qty}"


class GiftCampaignPlan(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected')
    )
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    item = models.ForeignKey(PromoItem, on_delete=models.CASCADE)
    month = models.IntegerField()
    year = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    manager_remark = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.employee.name} -> {self.doctor.name} ({self.item.name}) - {self.status}"


class DoctorROILedger(models.Model):
    date_given = models.DateField()
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, null=True, on_delete=models.SET_NULL)
    item = models.ForeignKey(PromoItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_value = models.DecimalField(max_digits=10, decimal_places=2)
    visit = models.ForeignKey('DCRVisit', null=True, blank=True, on_delete=models.SET_NULL, related_name='roi_entries', help_text="Kis visit ke through ye gift diya gaya. Visit delete hone par yahan se inventory reverse karne ke liye zaroori hai.")

    def __str__(self):
        return f"{self.doctor.name} received {self.item.name} (₹{self.total_value})"


def reverse_visit_inventory(visit):
    """
    Ek DCRVisit ko delete karne se PEHLE ye function call karna ZAROORI hai.
    Is visit ke through diye gaye saare Samples aur Gifts ko wapas
    MRInventory me jod deta hai, aur DoctorROILedger ki corresponding
    entries delete kar deta hai (taaki ROI report me purani/orphan
    gift entries permanently na reh jaayein).
    """
    employee = visit.daily_dcr.employee

    # 1. Samples wapas MRInventory me jodo
    for pd in visit.product_details.all():
        if pd.sample_qty > 0:
            sample_inv = MRInventory.objects.filter(
                employee=employee, item__linked_product=pd.product, item__item_type='Sample'
            ).first()
            if sample_inv:
                sample_inv.stock_qty += pd.sample_qty
                sample_inv.save()

    # 2. Gifts wapas MRInventory me jodo, aur ROI ledger entries hatao
    for entry in visit.roi_entries.all():
        inv = MRInventory.objects.filter(employee=entry.employee, item=entry.item).first()
        if inv:
            inv.stock_qty += entry.quantity
            inv.save()
        entry.delete()
# ==========================================
# ✏️ EDIT REQUEST TRACKERS (DOCTOR & CHEMIST)
# ==========================================
class ChemistEditRequest(models.Model):
    chemist = models.ForeignKey(Chemist, on_delete=models.CASCADE, related_name='edit_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    req_name = models.CharField(max_length=255)
    req_phone = models.CharField(max_length=50, null=True, blank=True)
    req_address = models.TextField(blank=True, null=True) # 🌟 BAS YE EK LINE ADD KARNI HAI
    req_territory = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True)
    req_route = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, default='Pending') 
    created_at = models.DateTimeField(auto_now_add=True)

class DoctorEditRequest(models.Model):
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name='edit_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    
    # 🌟 10 Editable Fields Tracker
    req_name = models.CharField(max_length=255)
    req_degree = models.CharField(max_length=100, null=True, blank=True)
    req_specialty = models.CharField(max_length=100, null=True, blank=True)
    req_category = models.CharField(max_length=10, null=True, blank=True)
    req_address = models.TextField(blank=True, null=True)
    req_residential_address = models.TextField(blank=True, null=True)  # 🌟 NAYA
    req_dom = models.DateField(blank=True, null=True)
    req_spouse_dob = models.DateField(blank=True, null=True)
    req_child_1_dob = models.DateField(blank=True, null=True)  # 🌟 NAYA
    req_child_2_dob = models.DateField(blank=True, null=True)  # 🌟 NAYA
    req_vcard_photo = models.ImageField(upload_to='doctor_vcards_requests/', blank=True, null=True)
    req_territory = models.ForeignKey(Territory, on_delete=models.SET_NULL, null=True, blank=True) # ⚠️ Missing tha
    req_route = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)
    req_mobile = models.CharField(max_length=50, null=True, blank=True)                            # ⚠️ Missing tha
    req_email = models.EmailField(null=True, blank=True)                                           # ⚠️ Missing tha
    req_dob = models.DateField(null=True, blank=True)                                              # ⚠️ Missing tha
    req_photo = models.ImageField(upload_to='doctor_photos/requests/', null=True, blank=True)
    
    # 🌟 System Fields
    status = models.CharField(max_length=20, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

# ==============================================================================
# 🔄 DATA TRANSFER AUDIT LOGS
# ==============================================================================
class EmployeeTransferLog(models.Model):
    transferred_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='transfers_made')
    old_employee_name = models.CharField(max_length=255) # Purane employee ka naam (jo inactive ho gaya)
    new_employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='transfers_received')
    details = models.TextField() # Kitne Doctor/Chemist transfer hue, status kya tha
    transfer_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer: {self.old_employee_name} -> {self.new_employee.name}"
        
        
class DeviceToken(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.employee.name} - {self.token[:10]}..."

class InternalMessage(models.Model):
    # 🌟 FIX: related_name change kiye 'sent_internal_messages' aur 'received_internal_messages'
    sender = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='sent_internal_messages')
    receiver = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='received_internal_messages')
    
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    sent_at = models.DateTimeField(auto_now_add=True)
    
    # 🌟 Reply/Forward ke liye parent message (Optional)
    parent_message = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replies')

    # 🌟 NAYA: Jab ek mail multiple logo ko jaaye, to sabke naam yahan store honge
    # taaki har recipient ko pata chale ki aur kisko bheja gaya tha (BCC jaisa na dikhe)
    all_recipients = models.CharField(max_length=500, blank=True, default='')

    def __str__(self):
        return f"From {self.sender} to {self.receiver}: {self.subject}"

class MessageAttachment(models.Model):
    message = models.ForeignKey(InternalMessage, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='email_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

# ------------------------------------------------------------------
# WEEKLY SECONDARY SALE & STOCK TRACKING MODELS (NEW)
# ------------------------------------------------------------------

class FocusProductTracking(models.Model):
    """
    RSM/Admin dwara set kiye gaye special products jinki field me tracking karni hai.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True) # False karne par app me dikhna band
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ek company me ek product ek hi baar active list me ho sakta hai
        unique_together = ('company', 'product')

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.product.name} ({status})"


class WeeklyStockistSaleMaster(models.Model):
    """
    Har Saturday MR jo Stockist ka total Value (Mandatory) daalega.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    stockist = models.ForeignKey(Stockist, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    week_ending_date = models.DateField() # Hamesha Saturday ki date hogi
    
    # Mandatory values in ₹
    total_sec_sale_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_closing_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ek stockist ka ek hafte ka ek hi record banega (Duplicate entry rokne ke liye)
        unique_together = ('stockist', 'week_ending_date')

    def __str__(self):
        return f"{self.stockist.name} - Week Ending: {self.week_ending_date}"


class WeeklyStockistSaleDetail(models.Model):
    """
    Focus Products ka Qty data (Optional) jo MR ne feed kiya ho.
    """
    master = models.ForeignKey(WeeklyStockistSaleMaster, related_name='details', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    
    # Qty in Box/Strips
    sec_sale_qty = models.PositiveIntegerField(default=0)
    closing_qty = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} - Sec: {self.sec_sale_qty}, Closing: {self.closing_qty}"

class CampaignControl(models.Model):
    """
    RSM/ZBM level par campaign (Secondary Sales/Focus Products) ko ON/OFF karne ka toggle.
    """
    manager = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='campaign_control')
    is_weekly_focus_active = models.BooleanField(default=False) # Default OFF rahega
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "ON" if self.is_weekly_focus_active else "OFF"
        return f"{self.manager.name} ({self.manager.designation}) - Focus Campaign: {status}"
# ==============================================================================
# 🌟 ACTIVITY & COMMUNITY HUB MODULE
# ==============================================================================

EVENT_CATEGORY_CHOICES = [
    ('Inauguration', 'Inauguration'),
    ('Medical Store', 'Medical Store'),
    ('CME', 'CME'),
    ('OPD Camp', 'OPD Camp'),
    ('Doctor RTD', 'Doctor RTD'),
    ('Birthday', 'Birthday'),
    ('Special Day', 'Special Day'),
    ('Other', 'Other'),
]

class FieldEvent(models.Model):
    employee = models.ForeignKey('Employee', related_name='field_events', on_delete=models.CASCADE)
    territory = models.ForeignKey('Territory', on_delete=models.SET_NULL, null=True, blank=True)
    doctor = models.ForeignKey('Doctor', on_delete=models.SET_NULL, null=True, blank=True)
    chemist = models.ForeignKey('Chemist', on_delete=models.SET_NULL, null=True, blank=True)
    
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    category = models.CharField(max_length=50, choices=EVENT_CATEGORY_CHOICES, default='Other')
    
    event_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # 🌟 Toggle for Community Wall (Agar True hai, toh sabko dikhega)
    is_shared_in_community = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.subject} - {self.employee.name} ({self.category})"


class EventPhoto(models.Model):
    event = models.ForeignKey(FieldEvent, related_name='photos', on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='events/photos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 🌟 IMAGE COMPRESSION LOGIC
        if self.photo and not self.id: # Sirf naye upload par compress kare
            im = Image.open(self.photo)
            
            # Agar image PNG (transparent) hai toh usko JPG format ke liye RGB mein convert karein
            if im.mode != 'RGB':
                im = im.convert('RGB')
                
            # Image ko resize karein (Max 1024x1024)
            im.thumbnail((1024, 1024))
            
            output = BytesIO()
            # 70% quality par JPG save karein (5MB ki photo ~200KB ho jayegi)
            im.save(output, format='JPEG', quality=70)
            output.seek(0)
            
            # Original file ko compressed file se replace karein
            file_name = self.photo.name.split('.')[0] + '.jpg'
            self.photo = InMemoryUploadedFile(
                output, 'ImageField', file_name, 
                'image/jpeg', sys.getsizeof(output), None
            )
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Photo for {self.event.subject}"


class EventLike(models.Model):
    event = models.ForeignKey(FieldEvent, related_name='likes', on_delete=models.CASCADE)
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Yeh rule ensure karega ki ek employee ek post ko sirf ek hi baar like kar paye
        unique_together = ('event', 'employee')

    def __str__(self):
        return f"{self.employee.name} liked {self.event.subject}"


class EventComment(models.Model):
    event = models.ForeignKey(FieldEvent, related_name='comments', on_delete=models.CASCADE)
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.employee.name} on {self.event.subject}"
