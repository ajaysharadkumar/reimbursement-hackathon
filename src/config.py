import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Project Root Directory ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Data & Receipts Directories ---
DATA_DIR = os.path.join(BASE_DIR, 'data')
RECEIPT_DIR = os.path.join(BASE_DIR, 'receipts')
RECORD_DIR = os.path.join(BASE_DIR, 'records')

# --- File Paths ---
EMPLOYEES_FILE = os.path.join(DATA_DIR, 'employees.csv')
POLICIES_FILE = os.path.join(DATA_DIR, 'expense_policies.csv')
TRAVEL_BOOKING_FILE = os.path.join(DATA_DIR, 'travel_bookings.csv')
VENDORS_FILE = os.path.join(DATA_DIR, 'vendors.csv')
REIMBURSEMENT_ACCOUNT_FILE = os.path.join(DATA_DIR, 'Reimbursement_Account.csv')
CLAIMS_FILE = os.path.join(RECORD_DIR, 'claims_log.csv')


# --- Environment Variables ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TARGET_EMAIL = os.getenv("TARGET_EMAIL")
COMPLIANCE_EMAIL = os.getenv("COMPLIANCE_EMAIL", "compliance@example.com")

# --- Gmail API Configuration ---
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_FILE = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(BASE_DIR, '..', 'token.json')