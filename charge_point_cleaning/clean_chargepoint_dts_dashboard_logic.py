"""Logic for the chargepoint data cleaning dashboard.

Pure data operations — no Streamlit UI calls.
"""

import os
import tempfile

from clean_datasets import clean_chargepoints


def clean_uploaded_file(uploaded_bytes: bytes, output_name: str) -> dict:
    """Clean an uploaded CSV file and return the result.

    Parameters
    ----------
    uploaded_bytes : bytes
        Raw bytes of the uploaded CSV file.
    output_name : str
        Desired output filename (e.g. ``all_charging_sites.csv``).

    Returns
    -------
    dict
        Keys: ``success`` (bool), ``error`` (str or None),
        ``output_path`` (str or None), ``cleaned_data`` (bytes or None).
    """
    # Save uploaded file to a temporary path
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded_bytes)
        input_path = tmp.name

    tmp_dir = tempfile.mkdtemp()
    output_path = os.path.join(tmp_dir, output_name)

    try:
        clean_chargepoints(input_path, output_path)
    except Exception as e:
        return {"success": False, "error": str(e), "output_path": None, "cleaned_data": None}

    if not os.path.exists(output_path):
        return {"success": False, "error": "Cleaning completed but output file not found.", "output_path": None, "cleaned_data": None}

    with open(output_path, "rb") as f:
        cleaned_data = f.read()

    return {"success": True, "error": None, "output_path": output_path, "cleaned_data": cleaned_data}


def save_to_dataset_folder(cleaned_data: bytes, filename: str, dataset_dir: str) -> str:
    """Save cleaned data to the dataset folder.

    Returns
    -------
    str
        Path where the file was saved.
    """
    os.makedirs(dataset_dir, exist_ok=True)
    dest_path = os.path.join(dataset_dir, filename)
    with open(dest_path, "wb") as fout:
        fout.write(cleaned_data)
    return dest_path
