# AI Expense Reimbursement Agent

This project is an autonomous AI agent designed to automate the end-to-end expense reimbursement process. It reads claims from an email inbox, performs multi-level validation, and routes them for approval, manager review, or compliance flagging based on a dynamic risk assessment.

## 🚀 Core Features

-   **Email Processing**: Automatically reads unread emails to find new expense claims.
-   **LLM-Powered Data Extraction**: Uses a Large Language Model (LLM) to intelligently extract claim details from unstructured email bodies (e.g., amount, category, vendor).
-   **OCR for Receipts**: Scans attached receipt images using OCR to extract text and validate claim data (amount, category).
-   **Automated Fraud Detection**:
    -   **Mismatch Detection**: Verifies that the amount and category from the email match the data extracted from the receipt.
    -   **Duplicate Check**: Checks the `claims_log.csv` file for existing claims with the same sender, amount, vendor, and category.
-   **Deep Policy Compliance**: Cross-references claims against multiple business rules:
    -   **Employee Validation**: Checks if the employee exists in `employees.csv`.
    -   **Policy Matching**: Finds the correct policy from `expense_policies.csv` based on the employee's grade and expense category.
    -   **Vendor Validation**: Ensures the vendor exists in `vendors.csv`, is verified, and matches the claimed expense category.
    -   **Amount Check**: Verifies the claim amount is within the policy's `max_allowance`.
-   **Intelligent Routing**: Triages claims based on their final risk level (`low`, `medium`, `high`):
    -   **Low Risk**: Auto-approves the claim.
    -   **Medium Risk**: Escalates to the employee's manager (e.g., for exceeding policy limits).
    -   **High Risk**: Rejects the claim and escalates it to the compliance team (e.g., for fraud, mismatch, or duplicate).
-   **Automated Email Generation**: Uses an LLM to generate professional, context-aware emails for approvals, rejections, and escalations.
-   **Persistent Logging**: Records every processed claim with its full state (status, risk, reasons) in a central `claims_log.csv` file.

## 📂 Project Structure

```
..
├── data/
│   ├── employees.csv
│   ├── expense_policies.csv
│   └── vendors.csv
│
├── records/
│   └── claims_log.csv
│
├── src/
│   ├── agent/
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   └── state.py
│   │
│   ├── services/
│   │   ├── email_service.py
│   │   └── ocr_service.py
│   │
│   ├── utils/
│   │   ├── data_loader.py
│   │   └── helpers.py
│   │
│   ├── config.py
│   └── main.py
│
└── README.md
```

## 💿 Data Files

The agent relies on three CSV files (assumed to be in a `data/` directory) for its compliance logic.

1.  **`employees.csv`**
    
    -   Contains the list of all employees.
    -   **Key Columns**: `employee_id`, `first_name`, `last_name`, `email`, `grade`, `manager_id`.
2.  **`expense_policies.csv`**
    
    -   Defines spending rules.
    -   **Key Columns**: `category`, `max_allowance`, `applicable_grades`.
3.  **`vendors.csv`**
    
    -   Lists all recognized vendors.
    -   **Key Columns**: `vendor_id`, `category`, `vendor_verified` (must be `TRUE` to be valid).

The agent automatically creates and appends to **`records/claims_log.csv`** upon first run.

---

## ⚙️ How It Works: The Agent's Logic Flow

The agent operates as a state machine (graph), passing the `ReimbursementState` between nodes.

1.  **Start**: The agent is triggered (e.g., by `main.py`).
2.  **`read_email_node`**: Fetches the oldest unread email. If it's a claim, it uses an LLM to extract initial data and save the receipt attachment.
3.  **`process_receipt_node`**: Runs OCR on the saved receipt to extract its text and then uses an LLM to find the `receipt_claim_amount` and `receipt_expense_category`.
4.  **`verify_claim_node`**: Compares the data from the email and the receipt. If they don't match, it flags `is_mismatched: True` and sets a rejection reason.
5.  **`fraud_and_anomaly_detection_node`**:
    -   Checks if `is_mismatched` is `True`.
    -   If not, it queries `claims_log.csv` to find duplicates.
    -   If a mismatch or duplicate is found, it sets `risk_level: 'high'` and `final_status: 'Rejected'`.
6.  **`policy_and_risk_assessment_node`**:
    -   Finds the employee in `employees.csv` to get their `grade` and `manager_email`.
    -   **If risk is already 'high'**: It skips all other checks and just returns the employee data (for logging).
    -   **If risk is 'low'**: It performs the full compliance check:
        1.  Finds a matching policy in `expense_policies.csv`.
        2.  Finds a matching vendor in `vendors.csv`.
        3.  Checks if `vendor_verified` is `TRUE`.
        4.  Checks if the `vendor.category` matches the `claim.category`.
        5.  Checks if `claim.amount` > `policy.max_allowance`.
    -   This node sets the `risk_level` to `medium` or `high` if any check fails.
7.  **`route_based_on_risk` (Conditional Edge)**:
    -   `risk_level == 'low'` ➔ routes to `auto_approve`.
    -   `risk_level == 'medium'` ➔ routes to `escalate_to_manager`.
    -   `risk_level == 'high'` ➔ routes to `escalate_to_compliance`.
8.  **Final Action Nodes**:
    -   **`auto_approve_node`**: Generates and sends an "Approved" email to the employee.
    -   **`escalate_to_manager_node`**: Generates and sends a "Review Required" email to the manager.
    -   **`escalate_to_compliance_node`**: Generates and sends a "Rejected" email to the employee *and* a "High-Risk Flag" email to the compliance team.
9.  **`update_google_sheet_node`**: Appends a new row to `records/claims_log.csv` with the complete final state of the claim.
10.  **End**: The graph finishes its run.

---

## 🛠️ Setup & Installation

1.  **Clone the Repository**
    
    ```bash
    git clone https://github.com/ajaykumar-dc/AgentMax-AI-Hackathon-Bengaluru.git
    ```
    
2.  **Install Dependencies** (You will need to create a `requirements.txt` file based on your project's imports)
    
    ```bash
    pip install -r requirements.txt
    ```
    
3.  **Set Environment Variables** Create a `.env` file in the root directory for your API keys and credentials:
    
    ```
    # OpenAI API Key
    OPENAI_API_KEY="sk-..."
    
    # Target Email Credentials (for reading/sending)
    TARGET_EMAIL="bangaloreaicoders@gmail.com"
    
    # Compliance Team Email
    COMPLIANCE_EMAIL="compliance@company.com"
    ```
    
4.  Make sure to place the `credentials.json` file in the **same directory** as your `.env` file. This is required to enable read and write access using the **Gmail API**.

---

## ▶️ How to Run

1.  Ensure all setup steps are complete.
2.  Run the `main.py` file to start the agent:
    
    ```bash
    python src/main.py
    ```
    
3.  The agent will start, initialize the `claims_log.csv` (if it doesn't exist), and begin processing unread emails.