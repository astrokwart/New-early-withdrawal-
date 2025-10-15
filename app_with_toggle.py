import pandas as pd
import streamlit as st
from datetime import datetime
import numpy as np

# --- Streamlit Page Setup ---
st.set_page_config(page_title="Early Withdrawal Checker", layout="wide")

st.title("🏦 Early Withdrawal Report Generator")
st.markdown(
    "Upload your **Deposit** and **Withdrawal** Excel files to identify early withdrawals. "
    "This version supports your file formats with headers such as *Value Date*, *Name*, *Account Number*, and *Amount*."
)

# --- File Uploaders ---
deposit_file = st.file_uploader("📥 Upload Deposit File", type=["xlsx"])
withdrawal_file = st.file_uploader("📥 Upload Withdrawal File", type=["xlsx"])

# --- Function to calculate working days ---
def working_days_between(start_date, end_date):
    try:
        return np.busday_count(start_date.date(), end_date.date())
    except Exception:
        return None

# --- If Deposit File Uploaded ---
if deposit_file:
    deposit_df = pd.read_excel(deposit_file)
    deposit_df.columns = deposit_df.columns.str.strip().str.lower()

    # Map your actual headers
    deposit_mapping = {
        "value date": "deposit_date",
        "name": "customer_name",
        "account number": "account_number",
        "credit amt": "amount"
    }

    deposit_df.rename(columns=deposit_mapping, inplace=True)

    # Add mobile banker column (blank if not in file)
    if "mobile_banker" not in deposit_df.columns:
        deposit_df["mobile_banker"] = None

    required_cols = ["deposit_date", "account_number", "customer_name", "mobile_banker", "amount"]
    missing = [c for c in required_cols if c not in deposit_df.columns]
    if missing:
        st.error(f"❌ Missing columns in Deposit file: {', '.join(missing)}")
    else:
        st.success("✅ Deposit file successfully standardized.")
        deposit_df["account_number"] = deposit_df["account_number"].astype(str)
        deposit_df["deposit_date"] = pd.to_datetime(deposit_df["deposit_date"], errors="coerce")
        deposit_df["amount"] = pd.to_numeric(deposit_df["amount"], errors="coerce")
        st.dataframe(deposit_df.head())

# --- If Withdrawal File Uploaded ---
if withdrawal_file:
    withdrawal_df = pd.read_excel(withdrawal_file)
    withdrawal_df.columns = withdrawal_df.columns.str.strip().str.lower()

    withdrawal_mapping = {
        "value date": "withdrawal_date",
        "name": "customer_name",
        "account number": "account_number",
        "amount": "amount"
    }

    withdrawal_df.rename(columns=withdrawal_mapping, inplace=True)

    required_cols = ["withdrawal_date", "account_number", "customer_name", "amount"]
    missing = [c for c in required_cols if c not in withdrawal_df.columns]
    if missing:
        st.error(f"❌ Missing columns in Withdrawal file: {', '.join(missing)}")
    else:
        st.success("✅ Withdrawal file successfully standardized.")
        withdrawal_df["account_number"] = withdrawal_df["account_number"].astype(str)
        withdrawal_df["withdrawal_date"] = pd.to_datetime(withdrawal_df["withdrawal_date"], errors="coerce")
        withdrawal_df["amount"] = pd.to_numeric(withdrawal_df["amount"], errors="coerce")
        st.dataframe(withdrawal_df.head())

# --- Continue only if both files uploaded and valid ---
if deposit_file and withdrawal_file:
    try:
        merged_df = pd.merge(deposit_df, withdrawal_df, on="account_number", how="left", suffixes=('', '_withdrawal'))

        # Calculate working days
        merged_df["working_days"] = merged_df.apply(
            lambda r: working_days_between(r["deposit_date"], r["withdrawal_date"])
            if pd.notnull(r["withdrawal_date"]) else None, axis=1
        )

        # Flag early withdrawals
        merged_df["early_withdrawal"] = merged_df["working_days"].apply(
            lambda x: x is not None and x < 14
        )

        # Option to filter early withdrawals
        apply_rule = st.checkbox("✅ Show only early withdrawals (within 14 working days)", value=True)

        if apply_rule:
            report_df = merged_df[merged_df["early_withdrawal"] == True]
            st.success(f"✅ Showing {len(report_df)} early withdrawals.")
        else:
            report_df = merged_df[pd.notnull(merged_df["withdrawal_date"])]
            st.success(f"📋 Showing all {len(report_df)} withdrawals matched to deposits.")

        # --- Group summary by Mobile Banker ---
        st.subheader("📊 Withdrawal Summary by Mobile Banker")
        summary = report_df.groupby("mobile_banker")["amount"].sum().reset_index()
        summary.rename(columns={"amount": "Total Withdrawal (GHS)"}, inplace=True)
        st.dataframe(summary)

        # --- Detailed Report ---
        st.subheader("📄 Detailed Withdrawal Report")
        st.dataframe(report_df[[
            "deposit_date", "customer_name", "account_number",
            "amount", "mobile_banker", "withdrawal_date", "working_days"
        ]])

        # --- Excel Download Button ---
        def to_excel(df):
            from io import BytesIO
            output = BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            return output.getvalue()

        st.download_button(
            label="⬇ Download Report as Excel",
            data=to_excel(report_df),
            file_name="withdrawal_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"❌ An error occurred while processing: {e}")
