import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Early Withdrawal Report", layout="wide")
st.title("🏦 Early Withdrawal Detection App")
st.write("Upload Deposit and Withdrawal Excel files to identify early withdrawals or view all withdrawals.")

# === Step 1: Upload files ===
deposit_file = st.file_uploader("📥 Upload Deposit File", type=["xlsx", "xls"])
withdrawal_file = st.file_uploader("📤 Upload Withdrawal File", type=["xlsx", "xls"])

# === Helper functions ===
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

        all_withdrawals = []

        # === Core logic: Match withdrawals to last deposit before withdrawal ===
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

            all_withdrawals.append({
                "Customer Name": w_row["customer_name"],
                "Account Number": acct,
                "Deposit Date": last_deposit["deposit_date"].date(),
                "Withdrawal Date": w_date.date(),
                "Working Days": days,
                "Deposit Amount": last_deposit["amount"],
                "Withdrawal Amount": w_row["amount"],
                "Early Withdrawal": days < 14
            })

        report_df = pd.DataFrame(all_withdrawals)

        # === Step 3: Checkbox filter ===
        st.subheader("🔍 Filter Option")
        apply_rule = st.checkbox("✅ Show only early withdrawals (within 14 working days)", value=True)

        if apply_rule:
            display_df = report_df[report_df["Early Withdrawal"] == True]
            st.success(f"✅ Showing {len(display_df)} early withdrawals (within 14 working days).")
        else:
            display_df = report_df
            st.info(f"📋 Showing all {len(display_df)} withdrawals matched to deposits.")

        # === Display Report ===
        st.subheader("📄 Withdrawal Report")
        st.dataframe(display_df, use_container_width=True)

        # === Download Function ===
        def to_excel(df):
            output = BytesIO()
            df.to_excel(output, index=False, engine="openpyxl")
            return output.getvalue()

        st.download_button(
            label="⬇ Download Withdrawal Report",
            data=to_excel(display_df),
            file_name="withdrawal_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        st.error(f"❌ Error while processing: {e}")
