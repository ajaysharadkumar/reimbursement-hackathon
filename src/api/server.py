import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agent.graph import app as agent_app

app = FastAPI(title="Reimbursement Auto Agent API")

def get_langfuse_handler():
    try:
        from langfuse.callback import CallbackHandler
        if os.getenv("LANGFUSE_SECRET_KEY"):
            return CallbackHandler()
    except Exception as e:
        print(f"Warning: langfuse callback init failed: {e}")
    return None

class ProcessRequest(BaseModel):
    trigger: str = "check_email"

@app.post("/api/v1/claims/process")
async def process_claims(req: ProcessRequest):
    """
    Triggers the Reimbursement Agent to fetch the oldest unread email and process it.
    """
    try:
        inputs = {}
        config_params = {}
        
        # Add Langfuse tracing if credentials are present
        lf_handler = get_langfuse_handler()
        if lf_handler:
            config_params["callbacks"] = [lf_handler]
            
        final_state = agent_app.invoke(inputs, config=config_params)
        
        if final_state and not final_state.get('receipt_path'):
            return {"status": "success", "message": "No new claims found to process."}
            
        return {
            "status": "success", 
            "message": f"Processed claim {final_state.get('claim_id')}. Final Status: {final_state.get('final_status')}",
            "data": {
                "claim_id": final_state.get('claim_id'),
                "final_status": final_state.get('final_status'),
                "risk_level": final_state.get('risk_level'),
                "rejection_reason": final_state.get('rejection_reason')
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/status")
async def root_status():
    return {"status": "FastAPI Agent Wrapper is running"}
