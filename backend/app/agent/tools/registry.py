"""The telco tools registered on the agent (the entrypoint adds them)."""

from app.agent.tools.account import explain_deductions, get_account_summary, get_usage_breakdown
from app.agent.tools.network import check_network_status
from app.agent.tools.packages import recommend_packages, search_packages
from app.agent.tools.rewards import get_offers_and_points
from app.agent.tools.support import get_case_status
from app.agent.tools.transactions import lookup_transactions


def telco_tools() -> list:
    return [
        get_account_summary,
        get_usage_breakdown,
        explain_deductions,
        search_packages,
        recommend_packages,
        lookup_transactions,
        get_offers_and_points,
        get_case_status,
        check_network_status,
    ]
