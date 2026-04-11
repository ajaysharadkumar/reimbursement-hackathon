from langgraph.graph import StateGraph, END
from src.agent.state import ReimbursementState
from src.agent import nodes

def create_workflow():
    """Creates the LangGraph workflow for expense reimbursement."""
    workflow = StateGraph(ReimbursementState)

    # Add nodes
    workflow.add_node("read_email", nodes.read_email_node)
    workflow.add_node("process_receipt", nodes.process_receipt_node)
    workflow.add_node("verify_claim", nodes.verify_claim_node)
    workflow.add_node("fraud_detection", nodes.fraud_and_anomaly_detection_node)
    workflow.add_node("policy_assessment", nodes.policy_and_risk_assessment_node)
    workflow.add_node("auto_approve", nodes.auto_approve_node)
    workflow.add_node("escalate_to_manager", nodes.escalate_to_manager_node)
    workflow.add_node("escalate_to_compliance", nodes.escalate_to_compliance_node)
    workflow.add_node("update_tracker", nodes.update_google_sheet_node)

    # Set entry point
    workflow.set_entry_point("read_email")

    # Add conditional edges
    workflow.add_conditional_edges(
        "read_email",
        lambda state: END if not state.get('receipt_path') else "process_receipt"
    )
    workflow.add_conditional_edges(
        "policy_assessment",
        nodes.route_based_on_risk
    )

    workflow.add_edge("process_receipt", "verify_claim")
    workflow.add_edge("verify_claim", "fraud_detection")
    workflow.add_edge("fraud_detection", "policy_assessment")
    workflow.add_edge("auto_approve", "update_tracker")
    workflow.add_edge("escalate_to_manager", "update_tracker")
    workflow.add_edge("escalate_to_compliance", "update_tracker")
    workflow.add_edge("update_tracker", END)

    return workflow.compile()

app = create_workflow()