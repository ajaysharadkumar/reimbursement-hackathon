import pandas as pd

def load_data(file_path):
    """Loads a CSV file into a pandas DataFrame."""
    try:
        return pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Warning: Data file not found at {file_path}")
        return None