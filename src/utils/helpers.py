from src import config
from src.utils import data_loader

# Load data once
employees_df = data_loader.load_data(config.EMPLOYEES_FILE)
policies_df = data_loader.load_data(config.POLICIES_FILE)


def get_manager_details(manager_id: str) -> str:
    """Finds a manager's email by their ID."""
    if employees_df is None:
        return ""
    manager = employees_df[employees_df['employee_id'] == manager_id]
    return manager.iloc[0]['email'] if not manager.empty else ""
