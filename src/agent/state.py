import operator
from typing import TypedDict, Annotated, List

from langchain_core.messages import BaseMessage


class reimbursementState(TypedDict):
    """
    Defines the structure of the state that flows through the graph.
    """
    claim_id: str
    email_content: str
    sender_email: str
    receipt_path: str
    extracted_text: str

    # Data from Email
    claim_amount: float
    expense_category: str
    vendor_id: str
    payment_mode: str
    date: str

    # Data from Receipt
    receipt_claim_amount: float
    receipt_expense_category: str
    is_mismatched: bool

    employee_details: dict
    policy_details: dict
    manager_email: str
    is_compliant: bool
    is_duplicate: bool
    rejection_reason: str
    risk_level: str  # 'low', 'medium', 'high'
    summary: str  # AI-generated summary for escalations
    final_status: str  # 'Approved', 'Rejected', 'Escalated'
    messages: Annotated[List[BaseMessage], operator.add]
