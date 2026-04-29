import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import re
from datetime import datetime, timedelta
import os

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

def get_file_label(file):
    return os.path.splitext(file.name)[0] if file else "Unknown"


def process_raw_deposits(df):
    records = []
    total_rows = len(df)
    for i in range(total_rows - 1):
        cell_b = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ""
        if cell_b.lower() == "txn":
            value_date = df.iloc[i, 0]
            raw_amt = str(df.iloc[i, 6]).strip()
            raw_amt = raw_amt.replace("'", "").replace("-", "").replace(",", "")
            try:
                amount = float(raw_amt)
            except:
                amount = 0.0
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
    records = []
    total_rows = len(df)
    for i in range(total_rows - 1):
        cell_b = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ""
        if cell_b == "Withdrawal":
            value_date = df.iloc[i, 0]
            raw_amt = df.iloc[i, 7]
            try:
                amount = float(raw_amt)
            except:
                amount = 0.0
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
    if pd.isna(start_date) or pd.isna(end_date):
        return None
    if start_date == end_date:
        return 0
    count = 0
    current = start_date + timedelta(days=1)
    while current <= end_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def match_original_logic(processed_deposits, processed_withdrawals):
    merged = pd.merge(
        processed_deposits.rename(columns={"Value Date": "Deposit Date", "Debit Amt": "Deposit Amt"}),
        processed_withdrawals.rename(columns={"Value Date": "Withdrawal Date", "Credit Amt": "Withdrawal Amt"}),
        on="Account Number",
        how="right",
        suffixes=("_DEP", "_WIT")
    )
    merged["Days Between"] = (merged["Withdrawal Date"] - merged["Deposit Date"]).dt.days
    merged = merged[(merged["Deposit Date"] <= merged["Withdrawal Date"]) | merged["Deposit Date"].isna()]
    merged["Status"] = merged["Days Between"].apply(
        lambda x: "EARLY WITHDRAWAL" if pd.notnull(x) and x < 14 else
                  "Normal" if pd.notnull(x) else "No Match"
    )
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


def highlight_status(row):
    if row["Status"] == "EARLY WITHDRAWAL":
        return ["background-color: #ffd6d6"] * len(row)
    elif row["Status"] == "Normal":
        return ["background-color: #d6f5d6"] * len(row)
    else:
        return ["background-color: #fff3cd"] * len(row)


def to_excel_multi_sheet(sheets_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def to_excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# ==============================================================
# FILE UPLOAD SECTION
# ==============================================================

st.markdown("### 📁 Upload Raw Files")

deposit_file = st.file_uploader("📥 Raw Deposits CSV", type=["csv", "xlsx"])

st.markdown("#### 📤 Withdrawal Files")
num_withdrawals = st.number_input(
    "How many withdrawal files do you want to upload?",
    min_value=1, max_value=20, value=1, step=1
)

withdrawal_files = []
num_cols = min(int(num_withdrawals), 3)
cols = st.columns(num_cols)
for idx in range(int(num_withdrawals)):
    col = cols[idx % num_cols]
    with col:
        wf = st.file_uploader(
            f"📤 Withdrawal File {idx + 1}",
            type=["csv", "xlsx"],
            key=f"wit_file_{idx}"
        )
        withdrawal_files.append(wf)

uploaded_withdrawal_files = [f for f in withdrawal_files if f is not None]

st.divider()

# ==============================================================
# PROCESSING
# ==============================================================

all_uploads_ready = (
    deposit_file is not None and
    len(uploaded_withdrawal_files) == int(num_withdrawals)
)

if deposit_file is not None and len(uploaded_withdrawal_files) < int(num_withdrawals):
    st.info(f"⬆️ {len(uploaded_withdrawal_files)}/{int(num_withdrawals)} withdrawal file(s) uploaded. Please upload the remaining file(s) to begin.")

if all_uploads_ready:
    deposit_name = get_file_label(deposit_file)

    with st.spinner("Processing raw files..."):

        # Process deposits
        try:
            if deposit_file.name.endswith(".csv"):
                raw_dep = pd.read_csv(deposit_file, header=None)
            else:
                raw_dep = pd.read_excel(deposit_file, header=None)
            processed_deposits = process_raw_deposits(raw_dep)
        except Exception as e:
            st.error(f"Error reading deposits file: {e}")
            st.stop()

        # Process each withdrawal file separately
        withdrawal_results = []
        for wf in uploaded_withdrawal_files:
            try:
                if wf.name.endswith(".csv"):
                    raw_wit = pd.read_csv(wf, header=None)
                else:
                    raw_wit = pd.read_excel(wf, header=None)
                processed_wit = process_raw_withdrawals(raw_wit)
                withdrawal_results.append((get_file_label(wf), processed_wit))
            except Exception as e:
                st.error(f"Error reading withdrawal file '{wf.name}': {e}")
                st.stop()

        # Combined withdrawals
        processed_withdrawals = pd.concat(
            [df for _, df in withdrawal_results], ignore_index=True
        ) if withdrawal_results else pd.DataFrame()

        # Generate report per withdrawal file
        per_file_reports = {}
        for wit_name, wit_df in withdrawal_results:
            if use_macro_logic:
                report = match_macro_logic(processed_deposits, wit_df)
            else:
                report = match_original_logic(processed_deposits, wit_df)
            per_file_reports[wit_name] = report

        combined_report = pd.concat(per_file_reports.values(), ignore_index=True) if per_file_reports else pd.DataFrame()

    st.success("✅ Files processed successfully!")

    # Summary metrics
    early_count = len(combined_report[combined_report["Status"] == "EARLY WITHDRAWAL"])
    normal_count = len(combined_report[combined_report["Status"] == "Normal"])
    no_match_count = len(combined_report[combined_report["Status"] == "No Match"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📥 Deposits", len(processed_deposits))
    m2.metric("📤 Withdrawals", len(processed_withdrawals))
    m3.metric("⚠️ Early Withdrawals", early_count)
    m4.metric("✅ Normal", normal_count)
    m5.metric("❓ No Match", no_match_count)

    days_label = "Working Days" if use_macro_logic else "Calendar Days"
    st.caption(f"ℹ️ Using **{'Macro Logic (Working Days)' if use_macro_logic else 'Original Logic (Calendar Days)'}** — Days Between column shows {days_label}.")

    st.divider()

    # Processed Deposits (named after file)
    st.markdown(f'<div class="section-header">📥 Processed Deposits — {deposit_name}</div>', unsafe_allow_html=True)
    st.dataframe(processed_deposits, use_container_width=True)

    # Processed Withdrawals (one section per file)
    for wit_name, wit_df in withdrawal_results:
        st.markdown(f'<div class="section-header">📤 Processed Withdrawals — {wit_name}</div>', unsafe_allow_html=True)
        st.dataframe(wit_df, use_container_width=True)

    st.divider()

    # Report per withdrawal file
    st.markdown("### 📊 Early Withdrawal Reports")
    for wit_name, report_df in per_file_reports.items():
        st.markdown(
            f'<div class="section-header">📊 {deposit_name} vs {wit_name}</div>',
            unsafe_allow_html=True
        )
        early_df = report_df[report_df["Status"] == "EARLY WITHDRAWAL"]
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("⚠️ Early", len(early_df))
        rc2.metric("✅ Normal", len(report_df[report_df["Status"] == "Normal"]))
        rc3.metric("❓ No Match", len(report_df[report_df["Status"] == "No Match"]))

        st.dataframe(report_df.style.apply(highlight_status, axis=1), use_container_width=True)

        if not early_df.empty:
            st.markdown(f"**⚠️ Early Withdrawals Only — {wit_name}**")
            st.dataframe(early_df, use_container_width=True)
        else:
            st.info(f"No early withdrawals found for {wit_name}.")

        st.divider()

    # Download section
    st.markdown("### 📥 Download Reports")

    all_sheets = {}
    all_sheets[f"Deposits - {deposit_name}"[:31]] = processed_deposits
    for wit_name, wit_df in withdrawal_results:
        all_sheets[f"Wit - {wit_name}"[:31]] = wit_df
    for wit_name, report_df in per_file_reports.items():
        all_sheets[f"Report - {wit_name}"[:31]] = report_df
    all_early = combined_report[combined_report["Status"] == "EARLY WITHDRAWAL"]
    all_sheets["All Early Withdrawals"] = all_early

    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button(
            label="📘 Full Report (All Sheets)",
            data=to_excel_multi_sheet(all_sheets),
            file_name=f"withdrawal_report_{deposit_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl2:
        st.download_button(
            label="⚠️ All Early Withdrawals",
            data=to_excel_download(all_early),
            file_name=f"early_withdrawals_{deposit_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl3:
        st.download_button(
            label="📥 Processed Deposits",
            data=to_excel_download(processed_deposits),
            file_name=f"processed_deposits_{deposit_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif deposit_file is None:
    st.info("⬆️ Please upload your raw deposits file and withdrawal file(s) to begin.")
