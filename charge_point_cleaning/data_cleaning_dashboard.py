"""Streamlit interface for cleaning raw Charge My Street charging site exports.

UI only — all logic lives in ``clean_chargepoint_dts_dashboard_logic.py``.

Usage:
    streamlit run data_cleaning_dashboard.py --server.port 8502
"""

import os
import streamlit as st

from clean_chargepoint_dts_dashboard_logic import clean_uploaded_file, save_to_dataset_folder


def main():
    st.set_page_config(page_title="CMS Data Cleaning Utility", layout="centered")
    st.title("CMS Data Cleaning Utility")
    st.markdown(
        """
        Use this tool to convert raw chargepoint exports into the standard
        format required by the CMS Grid Resilience dashboard.

        Upload your raw CSV file, and this tool will clean it into
        `all_charging_sites.csv` with the columns `charge_point_location`,
        `site_category`, `latitude`, and `longitude`.

        After cleaning, you can download the cleaned file or save it to
        the `dataset/` folder for use in the dashboard.
        """
    )

    # Add tabs for different cleaning options
    tab1, tab2 = st.tabs(["Charge My Street Data", "Borderlands Community Sites"])

    with tab1:
        _render_chargepoint_cleaning()

    with tab2:
        _render_borderlands_cleaning()


def _render_chargepoint_cleaning():
    """Render the Charge My Street data cleaning section."""
    uploaded_file = st.file_uploader("Upload raw chargepoint CSV file", type=["csv"])
    output_name = st.text_input(
        "Output file name",
        value="all_charging_sites.csv",
        help="Name of the cleaned file to save.",
    )

    if st.button("Clean dataset", key="clean_chargepoint"):
        if uploaded_file is None:
            st.warning("Please upload a CSV file before cleaning.")
            return

        result = clean_uploaded_file(uploaded_file.getbuffer(), output_name)

        if not result["success"]:
            st.error(f"Error cleaning dataset: {result['error']}")
            return

        st.success("Dataset cleaned successfully!")
        st.download_button(
            label="Download cleaned file",
            data=result["cleaned_data"],
            file_name=os.path.basename(result["output_path"]),
            mime="application/octet-stream",
        )

        dataset_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        if st.checkbox(f"Save to dataset folder for dashboard use", value=False, key="save_chargepoint"):
            dest_path = save_to_dataset_folder(result["cleaned_data"], output_name, dataset_dir)
            st.info(f"Saved cleaned file to {dest_path}")


def _render_borderlands_cleaning():
    """Render the Borderlands community sites cleaning section."""
    st.markdown(
        """
        Upload the Borderlands Long List Sites Excel file to clean and geocode
        community building locations for Charge My Street suggestions.

        **Required columns:** Town/ Village, Potential Sites, Brief Description, Local Authority Area
        """
    )

    uploaded_file = st.file_uploader("Upload Borderlands Excel file", type=["xlsx", "xls"])
    output_name = st.text_input(
        "Output file name",
        value="borderlands_community_sites.csv",
        help="Name of the cleaned file to save.",
        key="borderlands_output_name",
    )

    if st.button("Clean and geocode", key="clean_borderlands"):
        if uploaded_file is None:
            st.warning("Please upload an Excel file before cleaning.")
            return

        # Save uploaded file to temporary location
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.getbuffer())
            input_path = tmp.name

        # Import and run cleaning
        from clean_borderlands import clean_borderlands

        with st.spinner("Geocoding locations... This may take a few minutes."):
            result = clean_borderlands(input_path, output_name)

        # Clean up temporary file
        os.unlink(input_path)

        if not result["success"]:
            st.error(f"Error cleaning dataset: {result['error']}")
            return

        st.success(f"Borderlands data cleaned successfully!")
        st.info(f"Geocoded {result['geocoded_count']}/{result['total_count']} sites")

        # Read the output file for download
        with open(result["output_path"], "rb") as f:
            cleaned_data = f.read()

        st.download_button(
            label="Download cleaned file",
            data=cleaned_data,
            file_name=os.path.basename(result["output_path"]),
            mime="application/octet-stream",
        )

        dataset_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        if st.checkbox(f"Save to dataset folder for dashboard use", value=False, key="save_borderlands"):
            dest_path = save_to_dataset_folder(cleaned_data, output_name, dataset_dir)
            st.info(f"Saved cleaned file to {dest_path}")


if __name__ == "__main__":
    main()
