"""
SFA/api/core.py
================
🌟 MODULARIZED: Ye file ab sirf ek "re-export shim" hai — asli code
core_dayplan.py, core_visits.py, aur core_misc.py me split ho gaya hai
(kyunki original file 1000+ lines cross kar gayi thi).

Isse urls.py me KOI change nahi karni padi — `from SFA.api import core as
core_api` waisa hi chalega jaisa pehle chalta tha, kyunki saare functions
yahan wildcard-import ho kar available hain.

  core_dayplan.py  → api_dashboard, api_day_start, api_day_end, calculate_expense
  core_visits.py   → api_doctor_visit_detail, api_edit_visit, api_delete_visit
  core_misc.py     → notices, compliance alerts, location, notifications,
                      messages, vacancy list, my-requests, MTP handlers
"""

from .core_dayplan import *   # noqa: F401,F403
from .core_visits import *    # noqa: F401,F403
from .core_misc import *      # noqa: F401,F403
