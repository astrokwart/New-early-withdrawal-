import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Early Withdrawal Report", layout="wide")
st.title("🏦 Early Withdrawal Detection App")
st.write("Upload Deposit and Withdrawal Excel files to identify early withdrawals (within 14 working days).")

# === Step 1: Upload files ===
deposit_file = st.file_uploader("📥 Upload Deposit File", type=["xlsx", "xls"])
withdrawal_file = st.file_uploader("📤 Upload Withdrawal File", type=["xlsx", "xls"])

# === Helper function to read and clean files ===
def clean_deposit_file(file):
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip().str.lower()
    rename_map = {
        "value date": "deposit_date",
        "name": "customer_name",
        "account number": "account_number",
        "credit amt": "amount"
    }
    df.rename(columns=rename_map, inplace=True)
    df = df[["deposit_date", "customer_name", "account_number", "amount"]]
    return df

def clean_withdrawal_file(file):
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip().str.lower()
    rename_map = {
        "value date": "withdrawal_date",
        "name": "customer_name",
        "account number": "account_number",
        "amount": "amount"
    }
    df.rename(columns=rename_map, inplace=True)
    df = df[["withdrawal_date", "customer_name", "account_number", "amount"]]
    return df

# === Step 2: Process once both files are uploaded ===
if deposit_file and withdrawal_file:
    try:
        st.info("⏳ Processing files... Please wait.")

        deposit_df = clean_deposit_file(deposit_file)
        withdrawal_df = clean_withdrawal_file(withdrawal_file)

        deposit_df["deposit_date"] = pd.to_datetime(deposit_df["deposit_date"], errors="coerce")
        withdrawal_df["withdrawal_date"] = pd.to_datetime(withdrawal_df["withdrawal_date"], errors="coerce")

        deposit_df.sort_values(by=["account_number", "deposit_date"], inplace=True)
        withdrawal_df.sort_values(by=["account_number", "withdrawal_date"], inplace=True)

        early_withdrawals = []

        # === Core logic: Find early withdrawals ===
        for _, w_row in withdrawal_df.iterrows():
            acct = w_row["account_number"]
            w_date = w_row["withdrawal_date"]

            acct_deposits = deposit_df[
                (deposit_df["account_number"] == acct) &
                (deposit_df["deposit_date"] <= w_date)
            ]

            if acct_deposits.empty:
                continue

            last_deposit = acct_deposits.iloc[-1]
            days = np.busday_count(last_deposit["deposit_date"].date(), w_date.date())

            if days < 14:  # Early withdrawal condition
                early_withdrawals.append({
                    "Customer Name": w_row["customer_name"],
                    "Account Number": acct,
                    "Deposit Date": last_deposit["deposit_date"].date(),
                    "Withdrawal Date": w_date.date(),
                    "Working Days": days,
                    "Deposit Amount": last_deposit["amount"],
                    "Withdrawal Amount": w_row["amount"]
                })

        # === Step 3: Output results ===
        if early_withdrawals:
            report_df = pd.DataFrame(early_withdrawals)
            st.success(f"✅ Found {len(report_df)} early withdrawals (within 14 working days).")

            st.subheader("📄 Detailed Early Withdrawal Report")
            st.dataframe(report_df, use_container_width=True)

            # === Download ===
            def to_excel(df):
                output = BytesIO()
                df.to_excel(output, index=False, engine="openpyxl")
                return output.getvalue()

            st.download_button(
                label="⬇ Download Early Withdrawal Report",
                data=to_excel(report_df),
                file_name="early_withdrawal_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.info("✅ No early withdrawals detected. All withdrawals occurred after 14 working days.")

    except Exception as e:
        st.error(f"❌ Error while processing: {e}")
