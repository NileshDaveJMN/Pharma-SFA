"""
SFA/company_helpers.py
Company-filtered queryset helpers — SaaS ready
Use: from SFA.company_helpers import get_doctors, get_products, ...
"""
from SFA.models import (
    Doctor, Chemist, Product, Territory, Route,
    Stockist, PromoItem, Holiday, SystemSetting, CompanyNotice
)


def get_doctors(company, **kwargs):
    return Doctor.objects.filter(company=company, **kwargs)

def get_chemists(company, **kwargs):
    return Chemist.objects.filter(company=company, **kwargs)

def get_products(company, **kwargs):
    return Product.objects.filter(company=company, **kwargs)

def get_territories(company, **kwargs):
    return Territory.objects.filter(company=company, **kwargs)

def get_routes(company, **kwargs):
    return Route.objects.filter(company=company, **kwargs)

def get_stockists(company, **kwargs):
    return Stockist.objects.filter(company=company, **kwargs)

def get_promo_items(company, **kwargs):
    return PromoItem.objects.filter(company=company, **kwargs)

def get_holidays(company, **kwargs):
    return Holiday.objects.filter(company=company, **kwargs)

def get_notices(company, **kwargs):
    return CompanyNotice.objects.filter(company=company, **kwargs)

def get_system_setting(company):
    setting, _ = SystemSetting.objects.get_or_create(company=company)
    return setting
