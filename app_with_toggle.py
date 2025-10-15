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
        st.
