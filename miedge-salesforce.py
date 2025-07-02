import streamlit as st
import pandas as pd
import io
import warnings

st.set_page_config(
    page_title="PEO Analyzer",
    page_icon="🧾"
)

warnings.filterwarnings("ignore")

st.title("🔍 Unique PEO Extractor")
st.write("Upload a CSV or Excel file and we'll show you all the unique values in the **PEO (Normalized)** column.")

# Upload file
uploaded_file = st.file_uploader("📤 Upload CSV or Excel File", type=["csv", "xls", "xlsx"])

if uploaded_file:
    try:
        # Read the file regardless of format
        file_name = uploaded_file.name.lower()
        if file_name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif file_name.endswith((".xls", ".xlsx")):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file type.")
            st.stop()

        # Show preview
        st.success("✅ File uploaded and read successfully!")
        st.dataframe(df.head())

        if "PEO (Normalized)" in df.columns:
            unique_peos = sorted(df["PEO (Normalized)"].dropna().unique())
            st.markdown(f"### 🧾 Found {len(unique_peos)} unique PEO(s):")
            st.write(unique_peos)

            # Option to download them as a CSV
            peo_df = pd.DataFrame(unique_peos, columns=["PEO (Normalized)"])
            st.download_button(
                label="📥 Download Unique PEOs as CSV",
                data=peo_df.to_csv(index=False).encode("utf-8"),
                file_name="unique_peos.csv",
                mime="text/csv"
            )
        else:
            st.error("❌ The column `PEO (Normalized)` was not found in your file.")
    except Exception as e:
        st.error(f"❌ An error occurred: {e}")
