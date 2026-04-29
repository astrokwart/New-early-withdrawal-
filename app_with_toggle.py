import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
from datetime import datetime, timedelta

# --- Page config ---
st.set_page_config(
    page_title="Early Withdrawal Checker",
    page_icon="💰",
    layout="wide"
)

# --- Custom styling ---
st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .stDataFrame { border-radius: 10px; }
    .section-header {
        background: linear-gradient(90deg, #1e3a5f, #2563eb);
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        margin: 20px 0 10px 0;
        font-weight: bold;
        font-size: 16px;
    }
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

st.title("💰 Early Withdrawal Checker")
st.markdown("Upload your **raw bank statement CSV files** — the app will process and match them automatically.")

st.divider()

# --- Logic mode toggle ---
st.markdown("### ⚙️ Matching Logic")
lcol1, lcol2 = st.columns([1, 2])
with lcol1:
    use_macro_logic = st.toggle("Use Macro Logic (Working Days)", value=False)
with lcol2:
    if use_macro_logic:
        st.info("🔧 **Macro Logic** — Matches withdrawal to the **most recent deposit** before it. Uses **working days** (excludes weekends). Early = ≤ 14 working days.")
    else:
        st.info("📄 **Original Logic** — Matches withdrawal to **any deposit** within 14 days. Uses **calendar days** (includes weekends). Early = < 14 calendar days.")

st.divider()


# ==============================================================
# HELPER FUNCTIONS
# ==============================================================

def process_raw_deposits(df):
    """Extract txn rows from raw deposit CSV and return clean dataframe."""
    records = []
    total_rows = len(df)

    for i in range(total_rows - 1):
        cell_b = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ""

        if cell_b.lower() == "txn":
            value_date = df.iloc[i, 0]

            # Clean debit amount (col G = index 6)
            raw_amt = str(df.iloc[i, 6]).strip()
            raw_amt = raw_amt.replace("'", "").replace("-", "").replace(",", "")
            try:
                amount = float(raw_amt)
            except:
                amount = 0.0

            # Search next 1-4 rows for NAME-ACCOUNTNUMBER (16-digit acct)
            cust_name = ""
            acct_num = ""
            for j in range(i + 1, min(i + 5, total_rows)):
                name_acct = str(df.iloc[j, 1]).strip() if pd.notna(df.iloc[j, 1]) else ""
                dash_pos = name_acct.rfind("-")
                if dash_pos > 0:
                    potential_acct = name_acct[dash_pos + 1:].strip()
                    if len(potential_acct) == 16 and potential_acct.isdigit():
                        cust_name = name_acct[:dash_pos].strip()
                        acct_num = potential_acct
                        break

            records.append({
                "Value Date": pd.to_datetime(value_date, errors="coerce"),
                "Customer Name": cust_name,
                "Account Number": acct_num,
                "Debit Amt": amount
            })

    return pd.DataFrame(records)


def process_raw_withdrawals(df):
    """Extract Withdrawal rows from raw withdrawal CSV and return clean dataframe."""
    records = []
    total_rows = len(df)

    for i in range(total_rows - 1):
        cell_b = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ""

        if cell_b == "Withdrawal":
            value_date = df.iloc[i, 0]

            # Credit amount (col H = index 7)
            raw_amt = df.iloc[i, 7]
            try:
                amount = float(raw_amt)
            except:
                amount = 0.0

            # Search next 1-3 rows for NAME-ACCOUNTNUMBER (16-digit acct)
            cust_name = ""
            acct_num = ""
            for j in range(i + 1, min(i + 4, total_rows)):
                name_acct = str(df.iloc[j, 1]).strip() if pd.notna(df.iloc[j, 1]) else ""
                dash_pos = name_acct.rfind("-")
                if dash_pos > 0:
                    potential_acct = name_acct[dash_pos + 1:].strip()
                    if len(potential_acct) == 16 and potential_acct.isdigit():
                        cust_name = name_acct[:dash_pos].strip()
                        acct_num = potential_acct
                        break

            if acct_num:
                records.append({
                    "Value Date": pd.to_datetime(value_date, errors="coerce"),
                    "Customer Name": cust_name,
                    "Account Number": acct_num,
                    "Credit Amt": amount
                })

    return pd.DataFrame(records)


def count_working_days(start_date, end_date):
    """Count working days (Mon-Fri) between two dates."""
    if pd.isna(start_date) or pd.isna(end_date):
        return None
    if start_date == end_date:
        return 0
    count = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            count += 1
        current += timedelta(days=1)
    return count


def match_original_logic(processed_deposits, processed_withdrawals):
    """Original logic: any deposit within 14 calendar days of withdrawal."""
    merged = pd.merge(
        processed_deposits.rename(columns={"Value Date": "Deposit Date", "Debit Amt": "Deposit Amt"}),
        processed_withdrawals.rename(columns={"Value Date": "Withdrawal Date", "Credit Amt": "Withdrawal Amt"}),
        on="Account Number",
        how="right",
        suffixes=("_DEP", "_WIT")
    )
    merged["Days Between"] = (merged["Withdrawal Date"] - merged["Deposit Date"]).dt.days
    # Keep only deposits that are on or before withdrawal date
    merged = merged[(merged["Deposit Date"] <= merged["Withdrawal Date"]) | merged["Deposit Date"].isna()]
    merged["Status"] = merged["Days Between"].apply(
        lambda x: "EARLY WITHDRAWAL" if pd.notnull(x) and x < 14 else
                  "Normal" if pd.notnull(x) else "No Match"
    )
    # Use Customer Name from withdrawal side
    merged["Customer Name"] = merged["Customer Name_WIT"].combine_first(merged["Customer Name_DEP"])
    report_rows = []
    seen = set()
    for _, row in merged.iterrows():
        key = (str(row["Account Number"]), str(row["Withdrawal Date"]), str(row.get("Withdrawal Amt", "")))
        if key in seen:
            continue
        seen.add(key)
        report_rows.append({
            "Withdrawal Date": row["Withdrawal Date"],
            "Customer Name": row["Customer Name"],
            "Account Number": row["Account Number"],
            "Withdrawal Amt": row.get("Withdrawal Amt", None),
            "Deposit Date": row.get("Deposit Date", None),
            "Deposit Amt": row.get("Deposit Amt", None),
            "Days Between": row.get("Days Between", None),
            "Status": row["Status"]
        })
    return pd.DataFrame(report_rows)


def match_macro_logic(processed_deposits, processed_withdrawals):
    """Macro logic: most recent deposit before withdrawal, working days."""
    report_rows = []
    for _, wit_row in processed_withdrawals.iterrows():
        wit_acct = str(wit_row["Account Number"]).strip()
        wit_date = wit_row["Value Date"]
        matching_deps = processed_deposits[
            (processed_deposits["Account Number"] == wit_acct) &
            (processed_deposits["Value Date"] <= wit_date)
        ]
        if not matching_deps.empty:
            best_dep = matching_deps.loc[matching_deps["Value Date"].idxmax()]
            working_days = count_working_days(best_dep["Value Date"], wit_date)
            status = "EARLY WITHDRAWAL" if (working_days is not None and working_days <= 14) else "Normal"
            report_rows.append({
                "Withdrawal Date": wit_date,
                "Customer Name": wit_row["Customer Name"],
                "Account Number": wit_acct,
                "Withdrawal Amt": wit_row["Credit Amt"],
                "Deposit Date": best_dep["Value Date"],
                "Deposit Amt": best_dep["Debit Amt"],
                "Days Between": working_days,
                "Status": status
            })
        else:
            report_rows.append({
                "Withdrawal Date": wit_date,
                "Customer Name": wit_row["Customer Name"],
                "Account Number": wit_acct,
                "Withdrawal Amt": wit_row["Credit Amt"],
                "Deposit Date": None,
                "Deposit Amt": None,
                "Days Between": None,
                "Status": "No Match"
            })
    return pd.DataFrame(report_rows)


def to_excel_download(df):
    """Convert dataframe to Excel bytes for download."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ==============================================================
# FILE UPLOAD SECTION
# ==============================================================

st.markdown("### 📁 Upload Raw Files")

col1, col2 = st.columns(2)
with col1:
    deposit_file = st.file_uploader("📥 Raw Deposits CSV", type=["csv", "xlsx"])

with col2:
    two_files = st.toggle("Upload two withdrawal files?", value=False)

if two_files:
    wcol1, wcol2 = st.columns(2)
    with wcol1:
        withdrawal_file1 = st.file_uploader("📤 Raw Withdrawals CSV (File 1)", type=["csv", "xlsx"])
    with wcol2:
        withdrawal_file2 = st.file_uploader("📤 Raw Withdrawals CSV (File 2)", type=["csv", "xlsx"])
    withdrawal_files = [f for f in [withdrawal_file1, withdrawal_file2] if f is not None]
else:
    withdrawal_file1 = st.file_uploader("📤 Raw Withdrawals CSV", type=["csv", "xlsx"])
    withdrawal_files = [withdrawal_file1] if withdrawal_file1 else []

st.divider()

# ==============================================================
# PROCESSING
# ==============================================================

all_uploads_ready = deposit_file is not None and len(withdrawal_files) > 0
if two_files:
    all_uploads_ready = deposit_file is not None and len(withdrawal_files) == 2

if all_uploads_ready:
    with st.spinner("Processing raw files..."):

        # --- Read and process deposits ---
        try:
            if deposit_file.name.endswith(".csv"):
                raw_dep = pd.read_csv(deposit_file, header=None)
            else:
                raw_dep = pd.read_excel(deposit_file, header=None)
            processed_deposits = process_raw_deposits(raw_dep)
        except Exception as e:
            st.error(f"Error reading deposits file: {e}")
            st.stop()

        # --- Read and process withdrawals (one or two files) ---
        processed_list = []
        for wf in withdrawal_files:
            try:
                if wf.name.endswith(".csv"):
                    raw_wit = pd.read_csv(wf, header=None)
                else:
                    raw_wit = pd.read_excel(wf, header=None)
                processed_list.append(process_raw_withdrawals(raw_wit))
            except Exception as e:
                st.error(f"Error reading withdrawal file '{wf.name}': {e}")
                st.stop()

        processed_withdrawals = pd.concat(processed_list, ignore_index=True) if processed_list else pd.DataFrame()

        # --- Match deposits to withdrawals using selected logic ---
        if use_macro_logic:
            report_df = match_macro_logic(processed_deposits, processed_withdrawals)
        else:
            report_df = match_original_logic(processed_deposits, processed_withdrawals)

        # placeholder to keep indentation valid
        pass

    st.success("✅ Files processed successfully!")

    # --- Summary metrics ---
    early_count = len(report_df[report_df["Status"] == "EARLY WITHDRAWAL"])
    normal_count = len(report_df[report_df["Status"] == "Normal"])
    no_match_count = len(report_df[report_df["Status"] == "No Match"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📥 Deposits", len(processed_deposits))
    m2.metric("📤 Withdrawals", len(processed_withdrawals))
    m3.metric("⚠️ Early Withdrawals", early_count)
    m4.metric("✅ Normal", normal_count)
    m5.metric("❓ No Match", no_match_count)

    days_label = "Working Days" if use_macro_logic else "Calendar Days"
    st.caption(f"ℹ️ Using **{'Macro Logic (Working Days)' if use_macro_logic else 'Original Logic (Calendar Days)'}** — Days Between column shows {days_label}.")

    st.divider()

    # --- Processed Deposits ---
    st.markdown('<div class="section-header">📥 Processed Deposits</div>', unsafe_allow_html=True)
    st.dataframe(processed_deposits, use_container_width=True)

    # --- Processed Withdrawals ---
    st.markdown('<div class="section-header">📤 Processed Withdrawals</div>', unsafe_allow_html=True)
    st.dataframe(processed_withdrawals, use_container_width=True)

    # --- Full Report ---
    st.markdown('<div class="section-header">📊 Full Early Withdrawal Report</div>', unsafe_allow_html=True)

    def highlight_status(row):
        if row["Status"] == "EARLY WITHDRAWAL":
            return ["background-color: #ffd6d6"] * len(row)
        elif row["Status"] == "Normal":
            return ["background-color: #d6f5d6"] * len(row)
        else:
            return ["background-color: #fff3cd"] * len(row)

    st.dataframe(report_df.style.apply(highlight_status, axis=1), use_container_width=True)

    # --- Early Withdrawals only ---
    early_df = report_df[report_df["Status"] == "EARLY WITHDRAWAL"]
    st.markdown('<div class="section-header">⚠️ Early Withdrawals Only</div>', unsafe_allow_html=True)
    if not early_df.empty:
        st.dataframe(early_df, use_container_width=True)
    else:
        st.info("No early withdrawals found.")

    st.divider()

    # --- Download buttons ---
    st.markdown("### 📥 Download Reports")
    dl1, dl2, dl3, dl4 = st.columns(4)

    with dl1:
        st.download_button(
            label="📘 Full Report",
            data=to_excel_download(report_df),
            file_name="full_withdrawal_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl2:
        st.download_button(
            label="⚠️ Early Withdrawals",
            data=to_excel_download(early_df),
            file_name="early_withdrawals.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl3:
        st.download_button(
            label="📥 Processed Deposits",
            data=to_excel_download(processed_deposits),
            file_name="processed_deposits.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl4:
        st.download_button(
            label="📤 Processed Withdrawals",
            data=to_excel_download(processed_withdrawals),
            file_name="processed_withdrawals.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

else:
    if two_files:
        st.info("⬆️ Please upload your raw deposits file and both withdrawal files to begin.")
    else:
        st.info("⬆️ Please upload your raw deposits file and withdrawal file to begin.")
