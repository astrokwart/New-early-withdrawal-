import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import timedelta
import os

# --- Page config ---
st.set_page_config(
    page_title="Early Withdrawal Checker",
    page_icon="💰",
    layout="wide"
)

st.markdown("""
<style>
    .main { background-color: #f8fafc; }
    .section-header {
        background: linear-gradient(90deg, #1e3a5f, #2563eb);
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        margin: 20px 0 10px 0;
        font-weight: bold;
        font-size: 16px;
    }
    .dep-header {
        background: linear-gradient(90deg, #065f46, #059669);
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

# --- Logic toggle ---
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


def read_file(f):
    if f.name.endswith(".csv"):
        return pd.read_csv(f, header=None)
    else:
        return pd.read_excel(f, header=None)


# ==============================================================
# FILE UPLOAD SECTION
# ==============================================================

st.markdown("### 📁 Upload Raw Files")

# --- Deposit files ---
st.markdown("#### 📥 Deposit Files")
num_deposits = st.number_input(
    "How many deposit files do you want to upload?",
    min_value=1, max_value=20, value=1, step=1, key="num_dep"
)
deposit_files = []
dep_cols = st.columns(min(int(num_deposits), 3))
for idx in range(int(num_deposits)):
    col = dep_cols[idx % min(int(num_deposits), 3)]
    with col:
        df_up = st.file_uploader(
            f"📥 Deposit File {idx + 1}",
            type=["csv", "xlsx"],
            key=f"dep_file_{idx}"
        )
        deposit_files.append(df_up)

uploaded_deposit_files = [f for f in deposit_files if f is not None]

st.markdown("#### 📤 Withdrawal Files")
num_withdrawals = st.number_input(
    "How many withdrawal files do you want to upload?",
    min_value=1, max_value=20, value=1, step=1, key="num_wit"
)
withdrawal_files = []
wit_cols = st.columns(min(int(num_withdrawals), 3))
for idx in range(int(num_withdrawals)):
    col = wit_cols[idx % min(int(num_withdrawals), 3)]
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

total_dep_needed = int(num_deposits)
total_wit_needed = int(num_withdrawals)
all_uploads_ready = (
    len(uploaded_deposit_files) == total_dep_needed and
    len(uploaded_withdrawal_files) == total_wit_needed
)

if not all_uploads_ready:
    msgs = []
    if len(uploaded_deposit_files) < total_dep_needed:
        msgs.append(f"{len(uploaded_deposit_files)}/{total_dep_needed} deposit file(s)")
    if len(uploaded_withdrawal_files) < total_wit_needed:
        msgs.append(f"{len(uploaded_withdrawal_files)}/{total_wit_needed} withdrawal file(s)")
    st.info(f"⬆️ Uploaded: {' | '.join(msgs)}. Please upload all files to begin.")

if all_uploads_ready:
    with st.spinner("Processing raw files..."):

        # Process each deposit file
        deposit_results = []
        for df_up in uploaded_deposit_files:
            try:
                raw_dep = read_file(df_up)
                processed_dep = process_raw_deposits(raw_dep)
                deposit_results.append((get_file_label(df_up), processed_dep))
            except Exception as e:
                st.error(f"Error reading deposit file '{df_up.name}': {e}")
                st.stop()

        # Process each withdrawal file
        withdrawal_results = []
        for wf in uploaded_withdrawal_files:
            try:
                raw_wit = read_file(wf)
                processed_wit = process_raw_withdrawals(raw_wit)
                withdrawal_results.append((get_file_label(wf), processed_wit))
            except Exception as e:
                st.error(f"Error reading withdrawal file '{wf.name}': {e}")
                st.stop()

        # Combined deposits and withdrawals
        all_deposits = pd.concat([df for _, df in deposit_results], ignore_index=True)
        all_withdrawals = pd.concat([df for _, df in withdrawal_results], ignore_index=True)

        # Generate one report per DEPOSIT file (named after deposit)
        # Each deposit report matches that deposit's data against ALL withdrawals
        per_deposit_reports = {}
        for dep_name, dep_df in deposit_results:
            if use_macro_logic:
                report = match_macro_logic(dep_df, all_withdrawals)
            else:
                report = match_original_logic(dep_df, all_withdrawals)
            per_deposit_reports[dep_name] = report

        combined_report = pd.concat(per_deposit_reports.values(), ignore_index=True) if per_deposit_reports else pd.DataFrame()

    st.success("✅ Files processed successfully!")

    # Summary metrics
    early_count = len(combined_report[combined_report["Status"] == "EARLY WITHDRAWAL"])
    normal_count = len(combined_report[combined_report["Status"] == "Normal"])
    no_match_count = len(combined_report[combined_report["Status"] == "No Match"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("📥 Total Deposits", len(all_deposits))
    m2.metric("📤 Total Withdrawals", len(all_withdrawals))
    m3.metric("⚠️ Early Withdrawals", early_count)
    m4.metric("✅ Normal", normal_count)
    m5.metric("❓ No Match", no_match_count)

    days_label = "Working Days" if use_macro_logic else "Calendar Days"
    st.caption(f"ℹ️ Using **{'Macro Logic (Working Days)' if use_macro_logic else 'Original Logic (Calendar Days)'}** — Days Between column shows {days_label}.")

    st.divider()

    # --- Show processed deposits (one section per file) ---
    for dep_name, dep_df in deposit_results:
        st.markdown(f'<div class="dep-header">📥 Processed Deposits — {dep_name}</div>', unsafe_allow_html=True)
        st.dataframe(dep_df, use_container_width=True)

    # --- Show processed withdrawals (one section per file) ---
    for wit_name, wit_df in withdrawal_results:
        st.markdown(f'<div class="section-header">📤 Processed Withdrawals — {wit_name}</div>', unsafe_allow_html=True)
        st.dataframe(wit_df, use_container_width=True)

    st.divider()

    # --- Reports named after each deposit file ---
    st.markdown("### 📊 Early Withdrawal Reports")
    for dep_name, report_df in per_deposit_reports.items():
        st.markdown(
            f'<div class="dep-header">📊 Report — {dep_name}</div>',
            unsafe_allow_html=True
        )
        early_df = report_df[report_df["Status"] == "EARLY WITHDRAWAL"]
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("⚠️ Early", len(early_df))
        rc2.metric("✅ Normal", len(report_df[report_df["Status"] == "Normal"]))
        rc3.metric("❓ No Match", len(report_df[report_df["Status"] == "No Match"]))

        st.dataframe(report_df.style.apply(highlight_status, axis=1), use_container_width=True)

        if not early_df.empty:
            st.markdown(f"**⚠️ Early Withdrawals Only — {dep_name}**")
            st.dataframe(early_df, use_container_width=True)
        else:
            st.info(f"No early withdrawals found for {dep_name}.")

        # Download for this deposit file
        dep_sheets = {
            f"Report - {dep_name}"[:31]: report_df,
            f"Early - {dep_name}"[:31]: early_df,
        }
        st.download_button(
            label=f"📘 Download Report — {dep_name}",
            data=to_excel_multi_sheet(dep_sheets),
            file_name=f"report_{dep_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_dep_{dep_name}"
        )

        st.divider()

    # --- Combined download ---
    st.markdown("### 📥 Download All Reports")
    all_sheets = {}
    for dep_name, dep_df in deposit_results:
        all_sheets[f"Dep - {dep_name}"[:31]] = dep_df
    for wit_name, wit_df in withdrawal_results:
        all_sheets[f"Wit - {wit_name}"[:31]] = wit_df
    for dep_name, report_df in per_deposit_reports.items():
        all_sheets[f"Report - {dep_name}"[:31]] = report_df
    all_early = combined_report[combined_report["Status"] == "EARLY WITHDRAWAL"]
    all_sheets["All Early Withdrawals"] = all_early

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            label="📘 Full Report (All Sheets)",
            data=to_excel_multi_sheet(all_sheets),
            file_name="full_withdrawal_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with dl2:
        st.download_button(
            label="⚠️ All Early Withdrawals",
            data=to_excel_download(all_early),
            file_name="all_early_withdrawals.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
