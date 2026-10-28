"""The telco tools registered on the agent (the entrypoint adds them)."""

from app.agent.tools.account import explain_deductions, get_account_summary, get_usage_breakdown
from app.agent.tools.care_centres import find_care_centre
from app.agent.tools.network import check_network_status
from app.agent.tools.packages import purchase_package, recommend_packages, search_packages
from app.agent.tools.recharge import start_recharge
from app.agent.tools.rewards import get_offers_and_points, redeem_reward
from app.agent.tools.support import create_support_case, get_case_status, request_human_agent
from app.agent.tools.transactions import lookup_transactions
from app.agent.tools.verify import cancel_pending_action, verify_otp


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
        find_care_centre,
        purchase_package,
        start_recharge,
        redeem_reward,
        verify_otp,
        cancel_pending_action,
        create_support_case,
        request_human_agent,
    ]
