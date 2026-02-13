import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import base64
from io import BytesIO, StringIO

# ------------------------------
# Helper: background image
# ------------------------------
def load_bg_base64(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


# ------------------------------
# Screener search by company name
# ------------------------------
def find_screener_company_by_name(company_name):

    url = "https://www.screener.in/api/company/search/"

    r = requests.get(
        url,
        params={"q": company_name},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    r.raise_for_status()

    data = r.json()

    if not data:
        return None

    return "https://www.screener.in" + data[0]["url"]


# ------------------------------
# Scrape Screener tables by company name
# ------------------------------
def scrape_screener_financials_by_name(company_name, mode):

    company_url = find_screener_company_by_name(company_name)

    if not company_url:
        return None, {}

    # ---------------------------------
    # ALWAYS normalize base company URL
    # ---------------------------------
    company_url = company_url.replace("/consolidated/", "").rstrip("/") + "/"

    # ---------------------------------
    # Consolidated / Standalone switch
    # ---------------------------------
    if mode == "Consolidated":
        company_url = company_url + "consolidated/"

    r = requests.get(
        company_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    tables = soup.find_all("table")
    result = {}

    for idx, table in enumerate(tables, start=1):

        try:
            df = pd.read_html(StringIO(str(table)))[0]

            # -----------------------------
            # Fix "Raw PDF" links
            # -----------------------------
            rows = table.find_all("tr")

            for tr in rows:

                cells = tr.find_all(["th", "td"])
                if not cells:
                    continue

                first_cell_text = cells[0].get_text(strip=True)

                if first_cell_text.lower() == "raw pdf":

                    links = []
                    for td in cells[1:]:
                        a = td.find("a")
                        if a and a.get("href"):
                            href = a["href"]
                            if href.startswith("/"):
                                href = "https://www.screener.in" + href
                            links.append(href)
                        else:
                            links.append(None)

                    mask = (
                        df.iloc[:, 0]
                        .astype(str)
                        .str.strip()
                        .str.lower()
                        == "raw pdf"
                    )

                    if mask.any():
                        row_index = df[mask].index[0]

                        for i, link in enumerate(links):
                            if i + 1 < len(df.columns):
                                df.iat[row_index, i + 1] = link

        except Exception:
            continue

        # -----------------------------
        # Base section name
        # -----------------------------
        name = table.find_previous(["h2", "h3"])

        key = f"Table {idx}"
        if name:
            key = name.get_text(strip=True)

        # ------------------------------------------------
        # SMART rename for mini KPI tables
        # ------------------------------------------------
        try:
            if df.shape[1] == 2 and df.shape[0] <= 6:

                first_col = str(df.columns[0]).strip().lower()

                if "unnamed" in first_col:
                    label = str(df.iloc[0, 0]).strip()
                else:
                    label = str(df.columns[0]).strip()

                kpi_labels = {
                    "compounded sales growth",
                    "compounded profit growth",
                    "stock price cagr",
                    "return on equity"
                }

                if label.lower() in kpi_labels:
                    key = label

        except:
            pass

        # ---------------------------------------
        # Auto rename Shareholding Pattern tables
        # ---------------------------------------
        if key.lower().startswith("shareholding"):

            try:
                cols = list(df.columns)[1:]

                months = []
                for c in cols:
                    c = str(c).strip()
                    parts = c.split()
                    if len(parts) >= 1:
                        months.append(parts[0])

                non_mar = [m for m in months if m.lower() != "mar"]

                if len(non_mar) >= 3:
                    key = "Shareholding Pattern (Periodic)"
                else:
                    key = "Shareholding Pattern (Yearly)"

            except:
                pass

        # -----------------------------
        # Make key unique
        # -----------------------------
        base_key = key
        count = 1
        while key in result:
            count += 1
            key = f"{base_key} ({count})"

        result[key] = df

    return company_url, result

# ------------------------------
# Layout / health validation
# ------------------------------
def validate_core_sections(tables: dict):

    keys = [k.lower() for k in tables.keys()]

    checks = {
        "Profit & Loss": any("profit" in k and "loss" in k for k in keys),
        "Balance Sheet": any("balance" in k for k in keys),
        "Quarterly Results": any("quarter" in k for k in keys),
    }

    missing = [name for name, ok in checks.items() if not ok]
    return missing


# ------------------------------
# Excel download helper
# ------------------------------
def to_excel_bytes(dfs: dict):

    buf = BytesIO()
    writer = pd.ExcelWriter(buf, engine="openpyxl")

    for sheet, df in dfs.items():
        df.to_excel(writer, sheet_name=sheet[:31], index=False)

    writer.close()
    buf.seek(0)
    return buf


# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="FinXtract (Screener)", layout="wide")

bg_base64 = load_bg_base64(r"bg\bg-image.png")

st.markdown(f"""
<style>
.stApp {{
    background:
        linear-gradient(
            rgba(0, 0, 0, 0.45),
            rgba(0, 0, 0, 0.45)
        ),
        url("data:image/png;base64,{bg_base64}");
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}

h1,h2,h3,h4,p,label {{
    color: white !important;
}}

.stButton > button {{
    background: rgba(0,0,0,0.55);
    color: white;
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 10px;
}}

.screener-link {{
    font-size: 15px;
    font-weight: 600;
}}

.screener-link a {{
    color: #ffffff !important;
    text-decoration: underline;
}}

/* -----------------------------
   Dark glass table
----------------------------- */

.fin-table table {{
    width: 100%;
    border-collapse: collapse;
    background: rgba(15, 18, 25, 0.92);
    backdrop-filter: blur(6px);
}}

.fin-table th {{
    background: rgba(25, 28, 38, 0.95);
    color: #ffffff !important;
    font-weight: 600;
}}

.fin-table td {{
    color: #e6e6e6 !important;
}}

.fin-table th,
.fin-table td {{
    padding: 6px 10px;
    border: 1px solid rgba(255,255,255,0.08);
    font-size: 13px;
}}

.fin-table tr:hover td {{
    background: rgba(255,255,255,0.04);
}}

.fin-table a {{
    color: #6ea8ff;
    text-decoration: underline;
}}

/* -----------------------------
   Dark glass input box
----------------------------- */

div[data-baseweb="input"] > div {{
    background: rgba(15, 18, 25, 0.92) !important;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);

    border-radius: 8px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: none !important;
    min-height: 44px;
}}

div[data-baseweb="input"] > div > div {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}

div[data-baseweb="input"] input {{
    background: transparent !important;
    color: #e6e6e6 !important;
    font-size: 14px;
    padding: 10px 12px !important;
    outline: none !important;
    box-shadow: none !important;
}}

div[data-baseweb="input"] input::placeholder {{
    color: rgba(230,230,230,0.45) !important;
}}

div[data-baseweb="input"] > div:focus-within {{
    border: 1px solid rgba(110,168,255,0.6) !important;
    box-shadow: 0 0 0 1px rgba(110,168,255,0.25) !important;
}}

div[data-baseweb="input"] [aria-invalid="true"] {{
    border: none !important;
    box-shadow: none !important;
}}
</style>
""", unsafe_allow_html=True)

st.title("FinXtract • Screener Data")


# ------------------------------
# Session state
# ------------------------------
if "screener_tables" not in st.session_state:
    st.session_state.screener_tables = None

if "screener_company_url" not in st.session_state:
    st.session_state.screener_company_url = None

if "screener_company_name" not in st.session_state:
    st.session_state.screener_company_name = None

if "missing_sections" not in st.session_state:
    st.session_state.missing_sections = []


# ------------------------------
# FORM
# ------------------------------
with st.form("fetch_form"):
    company_input = st.text_input("Enter company name (as in Screener)")

    mode = st.radio(
        "Statement type",
        ["Consolidated", "Standalone"],
        horizontal=True
    )

    submit = st.form_submit_button("🚀 Fetch Financials")

# ------------------------------
# Fetch logic
# ------------------------------
if submit:

    if not company_input.strip():
        st.warning("Please enter a company name.")
    else:

        with st.spinner("Searching Screener and fetching financial tables..."):

            try:
                company_url, all_tables = scrape_screener_financials_by_name(
                    company_input.strip(), 
                    mode)


                st.session_state.screener_tables = all_tables
                st.session_state.screener_company_url = company_url
                st.session_state.screener_company_name = company_input.strip()

                if all_tables:
                    st.session_state.missing_sections = validate_core_sections(all_tables)
                else:
                    st.session_state.missing_sections = []

            except Exception as e:
                st.error(str(e))
                st.session_state.screener_tables = None
                st.session_state.screener_company_url = None
                st.session_state.screener_company_name = None
                st.session_state.missing_sections = []


# ------------------------------
# Display section
# ------------------------------
tables = st.session_state.screener_tables
company_url = st.session_state.screener_company_url
company_name = st.session_state.screener_company_name
missing = st.session_state.missing_sections

if tables:

    if missing:
        st.warning(
            "⚠ Possible Screener layout change detected. "
            f"Missing core sections: {', '.join(missing)}"
        )

    if company_url:
        st.markdown(
            f"""
            <div class="screener-link">
                🔗 Screener page :
                <a href="{company_url}" target="_blank">{company_url}</a>
            </div>
            """,
            unsafe_allow_html=True
        )

    for name, df in tables.items():
        st.subheader(name)

        df_show = df.copy()

        def make_link(v):
            if isinstance(v, str) and v.startswith("http"):
                return f'<a href="{v}" target="_blank">PDF</a>'
            return v

        df_show = df_show.map(make_link)

        st.markdown(
            f"<div class='fin-table'>{df_show.to_html(index=False, escape=False)}</div>",
            unsafe_allow_html=True
        )

    excel_buf = to_excel_bytes(tables)

    st.download_button(
        "⬇ Download All Financials as Excel",
        data=excel_buf,
        file_name=f"{company_name.replace(' ', '_')}_screener.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
