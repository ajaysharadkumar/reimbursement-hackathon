import streamlit as st
import pandas as pd
import requests
import os

st.set_page_config(page_title="AI Reimbursement Agent", page_icon="💸", layout="wide")

st.title("💸 AI-Powered Expense Reimbursement Agent")
st.markdown("This dashboard monitors the autonomous agent powered by LangGraph, Langfuse, and RAG.")

API_URL = "http://localhost:8000/api/v1/claims/process"
CLAIMS_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "records", "claims_log.csv")

col1, col2 = st.columns([1, 2])

with col1:
    st.header("Agent Control")
    if st.button("Trigger Email Processing", help="Force the agent to check the inbox right now.", use_container_width=True, type="primary"):
        with st.spinner("Agent is checking emails and processing claims..."):
            try:
                response = requests.post(API_URL, json={"trigger": "check_email"})
                if response.status_code == 200:
                    data = response.json()
                    if "No new claims" in data["message"]:
                        st.info("✅ No new claims found.")
                    else:
                        st.success(f"✅ {data['message']}")
                        st.json(data.get("data", {}))
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {e}")

with col2:
    st.header("Reimbursement Claims Log")
    if os.path.exists(CLAIMS_LOG_PATH):
        try:
            df = pd.read_csv(CLAIMS_LOG_PATH)
            # Display risk levels with colors
            def color_risk(val):
                color = 'green' if val == 'low' else 'orange' if val == 'medium' else 'red'
                return f'color: {color}'
                
            st.dataframe(df.style.applymap(color_risk, subset=['risk_level']), use_container_width=True)
        except Exception as e:
            st.warning("Claims log is empty or corrupted.")
    else:
        st.info("No claims processed yet. Claims Log will appear here.")
