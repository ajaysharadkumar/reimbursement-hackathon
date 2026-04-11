import json
import uuid
import re
import pandas as pd
import os
from datetime import datetime
from langchain_openai import ChatOpenAI
from src.agent.state import ReimbursementState
from src.utils import data_loader
from src.config import  EMPLOYEES_FILE, VENDORS_FILE, POLICIES_FILE, CLAIMS_FILE
from src.services import email_service, ocr_service
from src.utils.helpers import (
    get_manager_details,
)
from src.config import COMPLIANCE_EMAIL

def initialize_claims_file():
    """Checks if the claims file exists and creates it with headers if not."""
    try:
        # Get the directory from the file path
        RECORDS_DIR = os.path.dirname(CLAIMS_FILE)

        # Ensure the 'records' directory exists
        if RECORDS_DIR and not os.path.exists(RECORDS_DIR):
            os.makedirs(RECORDS_DIR)
            print(f"Created directory: {RECORDS_DIR}")

        # Check if the file itself exists
        if not os.path.isfile(CLAIMS_FILE):
            print(f"Claims file not found at {CLAIMS_FILE}. Creating it...")

            # Define the headers that update_google_sheet_node will use
            HEADERS = [
                'claim_id', 'timestamp', 'final_status', 'risk_level',
                'rejection_reason', 'summary', 'sender_email', 'employee_id',
                'employee_name', 'employee_grade', 'manager_email',
                'claim_amount', 'expense_category', 'vendor_id', 'date',
                'payment_mode', 'receipt_claim_amount', 'receipt_expense_category',
                'is_mismatched', 'is_compliant', 'is_duplicate', 'policy_category',
                'policy_max_allowance', 'policy_applicable_grades', 'receipt_path'
            ]

            # Create an empty DataFrame with these headers and save it
            df = pd.DataFrame(columns=HEADERS)
            df.to_csv(CLAIMS_FILE, index=False, header=True)
            print(f"✅ Successfully created claims file with headers: {CLAIMS_FILE}")

    except Exception as e:
        print(f"🛑 ERROR initializing claims file: {e}")
        print("Warning: Could not create claims file. Duplicate checks may be skipped.")


# Run the initialization check when this module is loaded
initialize_claims_file()

employees_df = data_loader.load_data(EMPLOYEES_FILE)
policies_df = data_loader.load_data(POLICIES_FILE)
vendors_df = data_loader.load_data(VENDORS_FILE)
claims_df = data_loader.load_data(CLAIMS_FILE)

# Initialize the Language Model
llm = ChatOpenAI(model="gpt-4o", temperature=0)


# Agent Nodes

def generate_email_content(llm, state: ReimbursementState, target_audience: str, purpose: str) -> dict:
    """
    Generates a professional email subject and body using the LLM.

    :param llm: The initialized ChatOpenAI instance.
    :param state: The current ReimbursementState.
    :param target_audience: Who the email is for ('employee', 'manager', 'compliance').
    :param purpose: The main goal of the email (e.g., 'Approval', 'Rejection', 'Manager Review', 'High-Risk Flag').
    :return: A dictionary with 'subject' and 'body'.
    """

    # Assemble all relevant data
    # This ensures the LLM stays in context by only giving it the facts.
    employee_details = state.get('employee_details', {})
    employee_name = f"{employee_details.get('first_name', 'User')}"

    context_data = {
        "claim_id": state.get('claim_id'),
        "employee_name": employee_name,
        "amount": state.get('claim_amount'),
        "category": state.get('expense_category'),
        "status": state.get('final_status'),
        "reason": state.get('rejection_reason'),
        "manager_email": state.get('manager_email'),
        "summary": state.get('summary')
    }

    # Create a specific prompt for the audience
    system_prompt = f"""
    You are an AI assistant for an automated expense system. Your task is to write a professional, clear, and concise email.
    
    *** CRITICAL INSTRUCTION ***
    All currency values MUST be prefixed with "INR " (e.g., "INR 123.45"). 
    Do NOT use any other currency symbol like '$' under any circumstances.
    
    Do NOT add any placeholders like [Your Name] or [Company Name].

    The tone should be:
    - For 'employee': Professional, clear, and helpful.
    - For 'manager': Direct, concise, and actionable.
    - For 'compliance': Formal, detailed, and factual.

    You will be given JSON data and a purpose. Generate a JSON object with "subject" and "body" keys.
    """

    user_prompt = f"""
    Generate an email for the following purpose:

    Target Audience: {target_audience}
    Purpose: {purpose}

    Key Data:
    {json.dumps(context_data, indent=2)}

    Instructions:
    - For 'employee' (Approval/Rejection): Address them by their name ({employee_name}). Clearly state the status (Approved/Rejected) and the reason if rejected.
    - For 'manager' (Manager Review): State that a claim from their direct report ({employee_name}) requires review. Mention the reason it was flagged (e.g., "exceeds policy limit").
    - For 'compliance' (High-Risk Flag): Formally state that a high-risk claim has been flagged and rejected. Detail the exact reason for the flag (e.g., "Data mismatch", "Duplicate claim").

    Return ONLY the JSON object.
    """

    prompt = (
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )

    try:
        response_content = llm.invoke(prompt).content
        # Clean the response to find the JSON
        json_start_index = response_content.find('{')
        json_end_index = response_content.rfind('}')
        if json_start_index != -1 and json_end_index != -1:
            json_string = response_content[json_start_index:json_end_index + 1]
            email_json = json.loads(json_string)
            return email_json
        else:
            raise ValueError("No JSON object found in LLM response.")

    except Exception as e:
        print(f"Error generating email content: {e}")
        # Fallback to a simple email if LLM fails
        return {
            "subject": f"Update on Claim {state.get('claim_id')}",
            "body": f"Your claim status is: {state.get('final_status')}. Reason: {state.get('rejection_reason')}"
        }

def read_email_node(state: ReimbursementState):
    """Reads the latest email, cleans the LLM response, and extracts receipt information."""
    print("---NODE: READING EMAIL---")
    email_data = email_service.read_unread_emails()
    if not email_data:
        print("No new claims found.")
        return {"receipt_path": None}

    claim_id = f"CL_{uuid.uuid4().hex[:6].upper()}"
    print(f"New claim received. Assigned ID: {claim_id}")
    text = email_data["email_content"]

    prompt = (
        [
            {
                "role": "system",
                "content": (
                    "You are a precision data extraction assistant. Your ONLY output must be a single, valid JSON object. "
                    "Do not include any explanatory text, markdown formatting, or apologies. "
                    "First, check if the email body contains keywords like 'reimbursement', 'claim', 'expense', 'receipt', or 'invoice'. "
                    "If not, respond ONLY with: {\"process\": false, \"reason\": \"Email not related to reimbursement\"}\n"
                    "If it is reimbursement-related, extract the following fields:\n"
                    "- 'employee_id'\n"
                    "- 'first_name'\n"
                    "- 'last_name'\n"
                    "- 'email_id'\n"
                    "- 'vendor_id'\n"
                    "- 'amount' (as a float, e.g., 123.45)\n"
                    "- 'category' (must be one of: Travel, Meals, Lodging, Office Supplies, Training, Other)\n"
                    "***IMPORTANT RULE: If the expense is for 'local conveyance', 'taxi', 'cab', or 'auto', you MUST map it to the 'Travel' category.***\n"
                    "- 'payment_mode'\n"
                    "- 'date'\n"
                    "If any field is missing, set its value to 'Not Found' or 'Unclear'. "
                    "The 'amount' must be a number; if ambiguous, set it to 0.0."
                )
            },
            {
                "role": "user",
                "content": f"Analyze the following email body and return ONLY the JSON object:\n\n---\nEmail Body:\n{text}\n---"
            }
        ]
    )
    response_content = llm.invoke(prompt).content
    extracted_data = {}

    try:
        # Clean the response to find the JSON
        json_start_index = response_content.find('{')
        json_end_index = response_content.rfind('}')
        if json_start_index != -1 and json_end_index != -1:
            json_string = response_content[json_start_index:json_end_index + 1]
            extracted_data = json.loads(json_string)
        else:
            print("Warning: No JSON object found in the LLM response.")
            extracted_data = {}  # Ensure extracted_data is a dict
    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse JSON from LLM response. Error: {e}")
        extracted_data = {}  # Ensure extracted_data is a dict

    # Check if the LLM flagged the email as irrelevant
    if not extracted_data.get("process", True):
        print(f"Email flagged as irrelevant. Reason: {extracted_data.get('reason')}")
        return {"receipt_path": None}

    amount_str = str(extracted_data.get("amount", "0.0"))
    cleaned_amount_str = re.sub(r'[^\d.]', '', amount_str)  # Remove currency, commas, etc.

    claim_amount = 0.0
    try:
        claim_amount = float(cleaned_amount_str) if cleaned_amount_str else 0.0
    except ValueError:
        print(f"Warning: Could not convert amount '{amount_str}' to float after cleaning. Defaulting to 0.0.")

    update = {
        "claim_id": claim_id,
        "email_content": text,
        "sender_email": email_data["sender_email"],
        "receipt_path": email_data["receipt_path"],
        "employee_details": {
            "employee_id": extracted_data.get("employee_id", "Not Found"),
            "first_name": extracted_data.get("first_name", "Not Found"),
            "last_name": extracted_data.get("last_name", "Not Found"),
            "email_id": extracted_data.get("email_id", "Not Found"),
        },
        "claim_amount": claim_amount,
        "expense_category": extracted_data.get("category", "Unclear").strip(),
        "vendor_id": extracted_data.get("vendor_id", "Not Found"),
        "payment_mode": extracted_data.get("payment_mode", "Not Found"),
        "date": extracted_data.get("date", "Not Found"),
    }

    print("Successfully Extracted Data from Email:")
    print(json.dumps(update, indent=4))
    return update


def process_receipt_node(state: ReimbursementState):
    """Processes the receipt using OCR and an LLM to extract details robustly."""
    print("---NODE: PROCESSING RECEIPT (OCR & LLM)---")
    text, _ = ocr_service.run_ocr_on_file(state['receipt_path'])

    prompt = (
        [
            {
                "role": "system",
                "content": (
                    "You are a precision data extraction assistant. Your ONLY output must be a single, valid JSON object. "
                    "Do not include any explanatory text or markdown.\n"
                    "Analyze the provided receipt text and return a JSON with these keys:\n"
                    "- 'amount' (the total amount as a float, e.g., 123.45)\n"
                    "- 'category' (must be one of: Travel, Meals, Lodging, Office Supplies, Training, Other)\n"
                    "***IMPORTANT RULE: If the receipt mentions 'local conveyance', 'taxi', 'cab', or 'auto', you MUST map it to the 'Travel' category.***\n"
                    "If a value is missing or ambiguous, set it to 0.0 or 'Unclear'."
                )
            },
            {
                "role": "user",
                "content": f"Analyze the following receipt text and return ONLY the JSON object:\n\n---\nReceipt Text:\n{text}\n---"
            }
        ]
    )
    response_content = llm.invoke(prompt).content
    extracted_data = {}

    try:
        json_start_index = response_content.find('{')
        json_end_index = response_content.rfind('}')
        if json_start_index != -1 and json_end_index != -1:
            json_string = response_content[json_start_index:json_end_index + 1]
            extracted_data = json.loads(json_string)
        else:
            print("Warning: No JSON object found in receipt LLM response.")
            extracted_data = {}
    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse JSON from receipt LLM response. Error: {e}")
        extracted_data = {}

    amount_str = str(extracted_data.get("amount", "0.0"))

    # Explicitly remove the comma
    cleaned_amount_str = amount_str.replace(',', '')

    # Use the regex to remove any remaining non-numeric characters
    cleaned_amount_str = re.sub(r'[^\d.]', '', cleaned_amount_str)

    receipt_amount = 0.0
    try:
        # Safely convert the fully cleaned string
        receipt_amount = float(cleaned_amount_str) if cleaned_amount_str else 0.0
    except ValueError:
        print(f"Warning: Could not convert receipt amount '{amount_str}' to float. Defaulting to 0.0.")

    update = {
        "extracted_text": text,
        "receipt_claim_amount": receipt_amount,
        "receipt_expense_category": extracted_data.get("category", "Unclear").strip()
    }

    print("Successfully Extracted Data from Receipt:")
    print(json.dumps(update, indent=4))
    return update


def verify_claim_node(state: ReimbursementState):
    """Compares data from email and receipt to check for discrepancies."""
    print("---NODE: VERIFYING CLAIM DATA---")

    email_amount = state.get('claim_amount', 0.0)
    receipt_amount = state.get('receipt_claim_amount', 0.0)
    email_category = state.get('expense_category', 'Unclear').lower()
    receipt_category = state.get('receipt_expense_category', 'Unclear').lower()

    # Allow a 1% tolerance for amount mismatches (e.g., OCR errors)
    amount_tolerance = email_amount * 0.01
    amounts_match = abs(email_amount - receipt_amount) <= amount_tolerance
    categories_match = email_category == receipt_category

    if amounts_match and categories_match:
        print("✅ Data matches between email and receipt.")
        return {"is_mismatched": False}
    else:
        reason = "Data mismatch between email and receipt."
        if not amounts_match:
            reason += f" Email Amount: INR {email_amount:.2f}, Receipt Amount: INR {receipt_amount:.2f}."
        if not categories_match:
            reason += f" Email Category: {state['expense_category']}, Receipt Category: {state['receipt_expense_category']}."

        print(f"🛑 MISMATCH DETECTED: {reason}")
        return {"is_mismatched": True, "rejection_reason": reason}

def fraud_and_anomaly_detection_node(state: ReimbursementState):
    print("\n---NODE: FRAUD & ANOMALY DETECTION---")

    # Extract fields safely
    sender = state.get("sender_email")
    amount = state.get("claim_amount")
    vendor_id = state.get("vendor_id")
    category = state.get("expense_category")
    receipt_path = state.get("receipt_path")
    employee_info = state.get("employee_details") or {}
    employee_id = employee_info.get("employee_id")

    # Initialize defaults
    risk_level = "low"
    rejection_reason = None
    is_duplicate = False
    hard_rejection = False  # Flag for hard rule violation

    # Check 1: Mismatch
    if state.get("is_mismatched"):
        print("⚠️ Mismatch detected between email and receipt.")
        risk_level = "high"
        rejection_reason = state.get("rejection_reason", "Data mismatch.")
        hard_rejection = True
    else:
        # Check 2: Duplicate
        if claims_df is not None:
            try:
                duplicates = claims_df[
                    (claims_df['sender_email'] == sender) &
                    (claims_df['claim_amount'] == amount) &
                    (claims_df['vendor_id'] == vendor_id) &
                    (claims_df['expense_category'] == category)
                    ]
                if len(duplicates) > 0:
                    print("🛑 Duplicate claim detected.")
                    risk_level = "high"
                    rejection_reason = "Duplicate claim with same amount, vendor, category, and receipt."
                    is_duplicate = True
                    hard_rejection = True
            except KeyError as e:
                print(f"⚠️ WARNING: KeyError during duplicate check. Column missing: {e}. Skipping check.")
        else:
            print("⚠️ WARNING: claims_df not loaded. Skipping duplicate check.")

    if not hard_rejection:
        print("✅ No mismatch or duplicate found. Claim looks clean.")

    # LLM Prompt for Final Decision
    final_status = "Approved"  # Default

    if hard_rejection:
        print("🛑 Hard rejection rule triggered. Setting status to Rejected.")
        final_status = "Rejected"
    else:
        # Only run LLM if no hard rejection has occurred.
        print("🧠 Calling LLM for soft fraud check...")
        prompt = [
            {
                "role": "system",
                "content": "You are a fraud-aware assistant that evaluates expense claims based on risk signals and metadata. Your job is to decide if the claim should be approved or flagged, and explain why."
            },
            {
                "role": "user",
                "content": (
                    "Evaluate the following claim and respond in this format:\n"
                    "Valid: Yes or No\n"
                    "Reason: Short explanation\n\n"
                    "Claim Details:\n"
                    f"- Sender Email: {sender}\n"
                    f"- Employee ID: {employee_id}\n"
                    f"- Expense Category: {category}\n"
                    f"- Claim Amount: ₹{amount}\n"
                    f"- Vendor ID: {vendor_id}\n"
                    f"- Receipt Path: {receipt_path}\n\n"
                    "Fraud Signals:\n"
                    f"- Mismatch Detected: {'Yes' if state.get('is_mismatched') else 'No'}\n"
                    f"- Duplicate Claim: {'Yes' if is_duplicate else 'No'}\n"
                    f"- Risk Level: {risk_level}\n"
                    f"- Rejection Reason: {rejection_reason or 'None'}\n\n"
                    "---\nRespond below:"
                )
            }
        ]

        response = llm.invoke(prompt).content
        print(f"\n🧠 LLM Decision:\n{response}\n")

        # Parse LLM Response
        valid = False
        reason = "Could not parse LLM response."
        for line in response.splitlines():
            if line.lower().startswith("valid:"):
                valid = line.split(":", 1)[1].strip().lower() == "yes"
            elif line.lower().startswith("reason:"):
                reason = line.split(":", 1)[1].strip()

        if not valid:
            risk_level = "high"  # LLM flagged it
            rejection_reason = reason
            final_status = "Rejected"
        else:
            final_status = "Approved"

    # Final Return
    return {
        "is_duplicate": is_duplicate,
        "risk_level": risk_level,
        "rejection_reason": rejection_reason,
        "final_status": final_status
    }


def policy_and_risk_assessment_node(state: ReimbursementState):
    """
    Checks employee, policy, and vendor compliance.
    This node is designed to *always* return the employee and policy
    details it finds, even if a compliance check fails,
    to ensure the state is fully populated for logging and escalations.
    """
    print("---NODE: POLICY & RISK ASSESSMENT---")

    # Initialize all state fields we will update
    updates = {
        "is_compliant": True,
        "risk_level": state.get('risk_level', 'low'),
        "rejection_reason": state.get('rejection_reason'),  # Start with existing reason
        "employee_details": {},
        "policy_details": {},
        "manager_email": "",
        "summary": state.get("summary", "")
    }
    # Set a default reason ONLY if none exists
    if updates["rejection_reason"] is None:
        updates["rejection_reason"] = "Claim is compliant."

    # Employee Lookup
    print("Employee check")
    if employees_df is None:
        print("❌ Employee data not loaded.")
        updates["is_compliant"] = False
        updates["rejection_reason"] = "Employee data could not be loaded."
        updates["risk_level"] = "high"
        return updates  # Hard exit

    employee_info = state.get("employee_details", {})
    Employee_ID = employee_info.get("employee_id")
    employee_data = employees_df[employees_df['employee_id'] == Employee_ID]

    if employee_data.empty:
        print(f"❌ Employee ID '{Employee_ID}' not found in database.")
        updates["is_compliant"] = False
        updates["rejection_reason"] = f"Employee ID '{Employee_ID}' not found in employee database."
        updates["risk_level"] = "high"
        return updates  # Hard exit

    # SUCCESS: Employee Found
    employee = employee_data.iloc[0].to_dict()
    # This data is needed for logs/escalations regardless of outcome
    employee_updates = {
        "employee_details": employee,
        "manager_email": get_manager_details(employee.get('manager_id', ''))
    }

    print(f"✅ Employee found → Name: {employee.get('first_name')}, Grade: {employee.get('grade')}")
    if not employee_updates["manager_email"]:
        print(f"⚠️ Warning: Manager email not found for manager_id '{employee.get('manager_id')}'")
    else:
        print(f"✅ Manager email found: {employee_updates['manager_email']}")

    # Check for pre-existing high risk
    if state.get('risk_level') == 'high':
        print("Skipping policy check; risk already set to 'high'.")
        return employee_updates

    # Policy & Vendor Waterfall Checks
    # This section now only runs if risk is NOT high
    category = state.get("expense_category")
    amount = state.get("claim_amount")
    vendor_id = state.get("vendor_id", "Not Found")
    grade = employee.get('grade')

    # Policy Lookup
    print("Policy check in progress")
    policy_match = pd.DataFrame()
    if policies_df is not None:
        if 'normalized_category' not in policies_df.columns:
            policies_df['normalized_category'] = policies_df['category'].str.lower().str.strip()
        if 'normalized_grades' not in policies_df.columns:
            policies_df['normalized_grades'] = policies_df['applicable_grades'].astype(str).str.replace(" ",
                                                                                                        "").str.upper().str.strip()

        normalized_category = category.lower().strip()
        normalized_grade = str(grade).upper()

        policy_match = policies_df[
            (policies_df['normalized_category'] == normalized_category) &
            (policies_df['normalized_grades'].apply(lambda g: normalized_grade in g.split(',')))
            ]

    if policy_match.empty:
        print("❌ No matching policy found.")
        updates["is_compliant"] = False
        updates["rejection_reason"] = f"No policy found for category '{category}' and grade '{grade}'."
        updates["risk_level"] = "medium"
        updates["final_status"] = "Rejected"
    else:
        policy = policy_match.iloc[0].to_dict()
        updates["policy_details"] = policy
        print(f"✅ Policy matched → Max Allowance: INR {policy.get('max_allowance')}")

    # Vendor Lookup (only if compliant so far)
    vendor = {}
    if updates["is_compliant"]:
        print("Vendor lookup is in progress")
        vendor_match = pd.DataFrame()
        if vendors_df is not None:
            if 'vendor_id' not in vendors_df.columns:
                for col in vendors_df.columns:
                    if 'vendor' in col.lower() and 'id' in col.lower():
                        vendors_df.rename(columns={col: 'vendor_id'}, inplace=True)
                        break
            if 'vendor_id' in vendors_df.columns:
                vendors_df['vendor_id'] = vendors_df['vendor_id'].astype(str).str.strip().str.upper()
                vendor_id_str = str(vendor_id).strip().upper()
                vendor_match = vendors_df[vendors_df['vendor_id'] == vendor_id_str]
            else:
                print("❌ Could not find 'vendor_id' column in vendors.csv.")
                updates["is_compliant"] = False
                updates["rejection_reason"] = "Vendor data is misconfigured (no 'vendor_id')."
                updates["risk_level"] = "high"

        if vendor_match.empty and updates["is_compliant"]:
            print("❌ Vendor not found.")
            updates["is_compliant"] = False
            updates["rejection_reason"] = f"Vendor ID '{vendor_id}' not found in vendor database."
            updates["risk_level"] = "medium"
        elif updates["is_compliant"]:
            vendor = vendor_match.iloc[0].to_dict()
            print(f"✅ Vendor matched → Verified: {vendor.get('vendor_verified')}")

    # Vendor Category Match (only if compliant so far)
    if updates["is_compliant"]:
        vendor_category = vendor.get("category", "").strip().lower()
        claim_category = category.strip().lower()
        if vendor_category != claim_category:
            print("❌ Vendor category mismatch.")
            updates["is_compliant"] = False
            updates[
                "rejection_reason"] = f"Vendor category '{vendor_category}' does not match claimed expense category '{claim_category}'."
            updates["risk_level"] = "high"

    # Vendor Verification (only if compliant so far)
    if updates["is_compliant"]:
        if str(vendor.get("vendor_verified", "False")).lower() != "true":
            print("❌ Vendor not verified.")
            updates["is_compliant"] = False
            updates["rejection_reason"] = f"Vendor '{vendor_id}' is not verified."
            updates["risk_level"] = "medium"
        else:
            print("Vendor verification complete")

    # Amount Check (only if compliant so far)
    max_allowance = 0.0
    if updates["is_compliant"]:
        policy = updates["policy_details"]
        max_allowance = float(policy.get('max_allowance', 0.0))
        if amount > max_allowance:
            print("⚠️ Amount exceeds policy limit.")
            updates["is_compliant"] = False
            updates[
                "rejection_reason"] = f"Amount INR {amount:.2f} exceeds policy limit of INR {max_allowance:.2f} and requires manager review."
            updates["risk_level"] = "medium"

    # Final Summary & Return
    summary = (
        f"Claim for INR {amount:.2f} (Category: {category}) by {employee.get('first_name')}. "
        f"Vendor: {vendor_id}. Policy Limit: INR {max_allowance:.2f}. "
        f"Status: {updates['rejection_reason']}"
    )
    updates["summary"] = summary

    print(
        f"Assessment complete. Risk: {updates['risk_level']}. Compliant: {updates['is_compliant']}. Reason: {updates['rejection_reason']}")

    # Return the *entire* updates dictionary *plus* the employee data
    updates.update(employee_updates)
    return updates


def auto_approve_node(state: ReimbursementState):
    """Approves a low-risk claim and notifies the employee."""
    print("---NODE: AUTO-APPROVING CLAIM (LOW RISK)---")

    # Call the LLM to generate the email
    email_content = generate_email_content(llm, state,
                                           target_audience='employee',
                                           purpose='Approval')

    print("\n--- LLM-Generated Email (Approval) ---")
    print(f"To: {state['sender_email']}")
    print(f"Subject: {email_content['subject']}")
    print("Body:")
    print(email_content['body'])
    print("----------------------------------------\n")

    # Send the LLM-generated email
    email_service.send_email(state['sender_email'],
                             email_content['subject'],
                             email_content['body'])

    print(f"Generated approval email for employee: {email_content['subject']}")
    return {"final_status": "Approved"}


def escalate_to_manager_node(state: ReimbursementState):
    """Escalates a medium-risk claim to the employee's manager."""
    print("---NODE: ESCALATING TO MANAGER (MEDIUM RISK)---")

    if state.get('manager_email'):
        # Call the LLM to generate the email
        email_content = generate_email_content(llm, state,
                                               target_audience='manager',
                                               purpose='Manager Review')

        print("\n--- LLM-Generated Email (Manager Escalation) ---")
        print(f"To: {state['manager_email']}")
        print(f"Subject: {email_content['subject']}")
        print("Body:")
        print(email_content['body'])
        print("----------------------------------------------\n")

        # Send the LLM-generated email
        email_service.send_email(state['manager_email'],
                                 email_content['subject'],
                                 email_content['body'])

        print(f"Escalation email sent to manager: {state['manager_email']}")
    else:
        print(f"🛑 Error: Manager email not found. Cannot escalate.")

    return {"final_status": "Escalated_To_Manager"}


def escalate_to_compliance_node(state: ReimbursementState):
    """Rejects a high-risk claim and escalates it to the compliance team."""
    print("---NODE: ESCALATING TO COMPLIANCE & REJECTING (HIGH RISK)---")

    # Notify employee of rejection
    employee_email = generate_email_content(llm, state,
                                            target_audience='employee',
                                            purpose='Rejection')

    print("\n--- LLM-Generated Email (Rejection) ---")
    print(f"To: {state['sender_email']}")
    print(f"Subject: {employee_email['subject']}")
    print("Body:")
    print(employee_email['body'])
    print("---------------------------------------\n")

    email_service.send_email(state['sender_email'],
                             employee_email['subject'],
                             employee_email['body'])

    # Notify compliance team
    compliance_email = generate_email_content(llm, state,
                                              target_audience='compliance',
                                              purpose='High-Risk Flag')

    print("\n--- LLM-Generated Email (Compliance Flag) ---")
    print(f"To: {COMPLIANCE_EMAIL}")
    print(f"Subject: {compliance_email['subject']}")
    print("Body:")
    print(compliance_email['body'])
    print("-------------------------------------------\n")

    email_service.send_email(COMPLIANCE_EMAIL,
                             compliance_email['subject'],
                             compliance_email['body'])

    print(f"Escalation email sent to compliance: {COMPLIANCE_EMAIL}")

    return {"final_status": "Rejected_And_Flagged"}

def update_google_sheet_node(state: ReimbursementState):
    """
    Updates the final status of the claim by appending a detailed
    record to the CSV file defined in config.CLAIMS_FILE.
    """
    print("---NODE: UPDATING CSV TRACKER---")

    try:
        CSV_FILE_PATH = CLAIMS_FILE

        # Safely extract all details from the state
        employee_details = state.get('employee_details', {})
        policy_details = state.get('policy_details', {})

        # Flatten the state into a single dictionary for the CSV row
        record = {
            'claim_id': state.get('claim_id'),
            'timestamp': datetime.now().isoformat(),
            'final_status': state.get('final_status'),
            'risk_level': state.get('risk_level'),
            'rejection_reason': state.get('rejection_reason'),
            'summary': state.get('summary'),
            'sender_email': state.get('sender_email'),
            'employee_id': employee_details.get('employee_id'),
            'employee_name': f"{employee_details.get('first_name', '')} {employee_details.get('last_name', '')}".strip(),
            'employee_grade': employee_details.get('grade'),
            'manager_email': state.get('manager_email'),
            'claim_amount': state.get('claim_amount'),
            'expense_category': state.get('expense_category'),
            'vendor_id': state.get('vendor_id'),
            'date': state.get('date'),
            'payment_mode': state.get('payment_mode'),
            'receipt_claim_amount': state.get('receipt_claim_amount'),
            'receipt_expense_category': state.get('receipt_expense_category'),
            'is_mismatched': state.get('is_mismatched'),
            'is_compliant': state.get('is_compliant'),
            'is_duplicate': state.get('is_duplicate'),
            'policy_category': policy_details.get('category'),
            'policy_max_allowance': policy_details.get('max_allowance'),
            'policy_applicable_grades': policy_details.get('applicable_grades'),
            'receipt_path': state.get('receipt_path')
        }

        # Define headers based on the record keys
        HEADERS = list(record.keys())

        # Create a DataFrame
        df = pd.DataFrame([record], columns=HEADERS)

        # Append to existing file without headers
        df.to_csv(CSV_FILE_PATH, mode='a', index=False, header=False)
        print(f"✅ Successfully appended to CSV tracker: {CSV_FILE_PATH}")

    except Exception as e:
        print(f"🛑 ERROR updating CSV tracker: {e}")

    return {}


# --- Conditional Router ---

def route_based_on_risk(state: ReimbursementState):
    """Routes the claim based on its assessed risk level."""
    risk_level = state.get('risk_level', 'high')  # Default to high risk if not set
    print(f"Routing based on risk level: {risk_level}")

    if risk_level == 'low':
        return "auto_approve"
    elif risk_level == 'medium':
        return "escalate_to_manager"
    else:  # 'high' / 'Out of Scope'
        return "escalate_to_compliance"