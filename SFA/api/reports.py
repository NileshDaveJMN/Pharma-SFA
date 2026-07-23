"""
SFA/api/reports.py
===================
🌟 MODULARIZED: Ye file ab sirf ek "re-export shim" hai — asli code
reports_helpers.py, reports_core.py, reports_approvals.py, aur
reports_ops.py me split ho gaya hai (kyunki original file 1000+ lines
cross kar gayi thi).

Isse urls.py me KOI change nahi karni padi — `from SFA.api import reports
as reports_api` waisa hi chalega jaisa pehle chalta tha, kyunki saare
functions yahan wildcard-import ho kar available hain.

  reports_helpers.py    → _resolve_selected_employee, _employee_brief (shared)
  reports_core.py       → api_product_sales_report, api_dcr_report, api_dcr_detail
  reports_approvals.py  → api_approval_hub, api_approval_action
  reports_ops.py        → network, product master, doctor-visit history,
                           inventory, free claims, tour plan, expense
                           report, holiday list
"""

from .reports_helpers import *    # noqa: F401,F403
from .reports_core import *       # noqa: F401,F403
from .reports_approvals import *  # noqa: F401,F403
from .reports_ops import *        # noqa: F401,F403
from .reports_secondary import *   # noqa: F401,F403
from .pob_reports import * # noqa: F401,F403
