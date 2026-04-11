import time
from src.agent.graph import app
from src import config
import os


def main():
    """Main function to run the expense reimbursement agent."""
    print("🚀 Agentic Expense Reimbursement Agent is running.")
    print("Press Ctrl+C to stop the agent.")

    if not os.path.exists(config.CREDENTIALS_FILE):
        print("\nERROR: `credentials.json` not found.")
        print("Please enable the Gmail API in your Google Cloud Console and download the credentials file.")
        return

    try:
        while True:
            print("\n" + "=" * 50)
            print("🔄 Checking for new expense claims...")

            inputs = {}
            final_state = app.invoke(inputs)

            if final_state and not final_state.get('receipt_path'):
                print("✅ No new claims found. Waiting for next check...")
            else:
                print("\n" + "-" * 50)
                print("✅ Claim processing complete.")
                print(f"   - Claim ID: {final_state.get('claim_id')}")
                print(f"   - Final Status: {final_state.get('final_status')}")
                print(f"   - Risk Level: {final_state.get('risk_level')}")
                print("-" * 50)

            time.sleep(30)

    except KeyboardInterrupt:
        print("\n\n🛑 Agent stopped by user.")
    except Exception as e:
        print(f"\n\n💥 An unexpected error occurred: {e}")


if __name__ == "__main__":
    # Ensure OPENAI_API_KEY is set
    if not config.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set. Please add it to your .env file.")
    main()