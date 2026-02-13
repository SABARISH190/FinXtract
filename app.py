# before running the application:
# Download below packages using pip:
# Just Copy and Paste in your terminal:
# pip install arelle-release pandas openpyxl requests streamlit

# and next run the app using:
# streamlit run app.py



import streamlit as st
import pandas as pd
import requests
from arelle import Cntlr
import xml.etree.ElementTree as ET
import tempfile
import os
import zipfile
from urllib.parse import urlparse
import shutil
from io import BytesIO
import base64


# ----------------------------------------
# Downloader
# ----------------------------------------

def download_to_temp(url, suffix):

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": url
    }

    session = requests.Session()

    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
    except:
        pass

    r = session.get(url, headers=headers, timeout=60)
    r.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()

    return tmp.name


# ----------------------------------------
# Arelle extractor (XML + iXBRL)
# ----------------------------------------

def extract_with_arelle_full(path):

    cntlr = Cntlr.Cntlr(logFileName=None)
    model = cntlr.modelManager.load(path)

    rows = []

    for fact in model.facts:

        ctx = fact.context

        entity = None
        period = None
        dimensions = []

        if ctx is not None and ctx.entityIdentifier is not None:
            entity = ctx.entityIdentifier[1]

        if ctx is not None and ctx.period is not None:
            period = ctx.period.stringValue

        if ctx is not None and ctx.qnameDims is not None:
            for dim, mem in ctx.qnameDims.items():

                dim_name = dim.localName if dim is not None else None

                mem_name = None
                if mem is not None and mem.memberQname is not None:
                    mem_name = mem.memberQname.localName

                if dim_name and mem_name:
                    dimensions.append(f"{dim_name}:{mem_name}")

        concept_name = None
        if fact.concept is not None and fact.concept.qname is not None:
            concept_name = fact.concept.qname.localName

        unit_val = None
        if fact.unit is not None:
            unit_val = fact.unit.value

        rows.append({
            "Concept": concept_name,
            "Value": fact.value,
            "Entity": entity,
            "Period": period,
            "Unit": unit_val,
            "Decimals": fact.decimals,
            "Dimensions": ",".join(dimensions) if dimensions else None
        })

    return rows


# ----------------------------------------
# XML fallback (only for real instance XML)
# ----------------------------------------

def extract_with_xml_fallback(path):

    tree = ET.parse(path)
    root = tree.getroot()

    ns = {
        "xbrli": "http://www.xbrl.org/2003/instance",
        "xbrldi": "http://xbrl.org/2006/xbrldi"
    }

    context_map = {}

    for ctx in root.findall("xbrli:context", ns):

        cid = ctx.attrib.get("id")

        entity = None
        start = None
        end = None
        instant = None
        dims = []

        ident = ctx.find(".//xbrli:identifier", ns)
        if ident is not None:
            entity = ident.text

        s = ctx.find(".//xbrli:startDate", ns)
        e = ctx.find(".//xbrli:endDate", ns)
        i = ctx.find(".//xbrli:instant", ns)

        if s is not None:
            start = s.text
        if e is not None:
            end = e.text
        if i is not None:
            instant = i.text

        for mem in ctx.findall(".//xbrldi:explicitMember", ns):
            dims.append(mem.text)

        context_map[cid] = {
            "entity": entity,
            "period": f"{start} to {end}" if start and end else instant,
            "dims": ",".join(dims) if dims else None
        }

    rows = []

    for el in root.iter():

        if "contextRef" not in el.attrib:
            continue

        tag = el.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]

        cid = el.attrib.get("contextRef")
        ctx = context_map.get(cid, {})

        rows.append({
            "Concept": tag,
            "Value": el.text,
            "Entity": ctx.get("entity"),
            "Period": ctx.get("period"),
            "Unit": el.attrib.get("unitRef"),
            "Decimals": None,
            "Dimensions": ctx.get("dims")
        })

    return rows


# ----------------------------------------
# Process a single local file
# ----------------------------------------

def process_one_local_file(path):

    ext = os.path.splitext(path)[1].lower()

    rows = extract_with_arelle_full(path)

    if len(rows) == 0 and ext in [".xml", ".xbrl"]:
        rows = extract_with_xml_fallback(path)

    return rows


# ----------------------------------------
# Main processor for one URL
# ----------------------------------------

def process_url(url):

    suffix = os.path.splitext(urlparse(url).path)[1]
    if not suffix:
        suffix = ".dat"

    temp_path = download_to_temp(url, suffix)

    all_rows = []

    try:

        if suffix.lower() == ".zip":

            work_dir = tempfile.mkdtemp()

            with zipfile.ZipFile(temp_path, "r") as z:
                z.extractall(work_dir)

            for root, _, files in os.walk(work_dir):
                for f in files:
                    lf = f.lower()
                    if lf.endswith((".xml", ".xbrl", ".html", ".xhtml")):
                        full = os.path.join(root, f)
                        all_rows.extend(process_one_local_file(full))

            shutil.rmtree(work_dir, ignore_errors=True)

        else:
            all_rows = process_one_local_file(temp_path)

    finally:
        try:
            os.remove(temp_path)
        except:
            pass

    return all_rows


# ----------------------------------------
# Auto P&L sheet
# ----------------------------------------

def build_pl_sheet(df):

    pl_concepts = [
        "RevenueFromOperations",
        "OtherIncome",
        "Income",
        "EmployeeBenefitExpense",
        "FinanceCosts",
        "DepreciationDepletionAndAmortisationExpense",
        "OtherExpenses",
        "Expenses",
        "ProfitBeforeExceptionalItemsAndTax",
        "ProfitBeforeTax",
        "TaxExpense",
        "ProfitLossForPeriod"
    ]

    out = df[df["Concept"].isin(pl_concepts)].copy()

    if out.empty:
        return out

    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")

    order = {c: i for i, c in enumerate(pl_concepts)}
    out["_o"] = out["Concept"].map(order)

    out = out.sort_values(["Period", "_o"]).drop(columns="_o")

    return out


# ----------------------------------------
# Auto Balance Sheet
# ----------------------------------------

def build_bs_sheet(df):

    bs_concepts = [
        "Assets",
        "NonCurrentAssets",
        "CurrentAssets",
        "Equity",
        "EquityAndLiabilities",
        "NonCurrentLiabilities",
        "CurrentLiabilities",
        "TotalAssets",
        "TotalEquity",
        "TotalLiabilities"
    ]

    out = df[df["Concept"].isin(bs_concepts)].copy()

    if out.empty:
        return out

    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")

    return out

def load_bg_base64(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


# ----------------------------------------
# Streamlit UI
# ----------------------------------------

st.set_page_config(page_title="FinXtract", layout="wide")

# ---------- Background image with dim overlay ----------
bg_base64 = load_bg_base64(r"bg\bg-image.png")

st.markdown(
    f"""
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

    /* Headings and labels */
    h1, h2, h3, h4, h5, h6, p, label {{
        color: #ffffff !important;
    }}

    /* ===== Text area – light glass (not too dark) ===== */

    /* outer textarea container */
    div[data-baseweb="textarea"] {{
        background: transparent !important;
    }}

    /* glass wrapper (this is the visible box) */
    div[data-baseweb="textarea"] > div {{
        background: transparent !important;   /* light glass */
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.25) !important;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        box-shadow: none !important;
    }}

    /* actual textarea */
    div[data-baseweb="textarea"] textarea {{
        background: transparent !important;
        color: #ffffff !important;
        border: none !important;
    }}

    /* placeholder */
    div[data-baseweb="textarea"] textarea::placeholder {{
        color: rgba(255,255,255,0.6);
    }}

    /* Buttons */
    .stButton > button {{
        background: rgba(0,0,0,0.55);
        color: white;
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 10px;
        backdrop-filter: blur(8px);
    }}

    /* Dataframes stay readable */
    .stDataFrame, .stTable {{
        background-color: rgba(255, 255, 255, 0.96);
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# ---------- App header ----------

st.title("FinXtract")

st.markdown(
    "Paste NSE or BSE XBRL / iXBRL links separated by commas.\n\n"
    "Supports: xml, xbrl, html (iXBRL), xhtml, zip\n\n"
    "Each link is shown separately.\n\n"
    "Inside every link you will get **P&L tab** and **Balance Sheet tab**."
)

links_text = st.text_area(
    "Links (comma separated)",
    height=140
)

if "results" not in st.session_state:
    st.session_state.results = []

if st.button("🚀 Process"):

    urls = [u.strip() for u in links_text.split(",") if u.strip()]

    st.session_state.results = []

    for idx, url in enumerate(urls, start=1):

        with st.spinner(f"Processing file {idx} ..."):

            try:
                rows = process_url(url)

                if not rows:
                    st.session_state.results.append({
                        "index": idx,
                        "error": "No facts found"
                    })
                    continue

                df = pd.DataFrame(rows)

            except Exception as e:
                st.session_state.results.append({
                    "index": idx,
                    "error": str(e)
                })
                continue

            st.session_state.results.append({
                "index": idx,
                "df": df
            })


# ----------------------------------------
# Display results in tabs per link
# ----------------------------------------

if st.session_state.results:

    st.divider()

    for item in st.session_state.results:

        st.subheader(f"XBRL file {item['index']}")

        if "error" in item:
            st.error(item["error"])
            continue

        df = item["df"]

        pl_df = build_pl_sheet(df)
        bs_df = build_bs_sheet(df)

        tab_pl, tab_bs, tab_all = st.tabs(
            ["📊 Profit & Loss", "🏦 Balance Sheet", "📄 All extracted facts"]
        )

        # ---------------- P&L TAB ----------------

        with tab_pl:

            if pl_df.empty:
                st.info("No Profit & Loss concepts found in this filing.")
            else:
                st.dataframe(pl_df, use_container_width=True)

                buf = BytesIO()
                pl_df.to_excel(buf, index=False, engine="openpyxl")
                buf.seek(0)

                st.download_button(
                    "⬇ Download P&L sheet",
                    data=buf,
                    file_name=f"xbrl_pl_{item['index']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # ---------------- BALANCE SHEET TAB ----------------

        with tab_bs:

            if bs_df.empty:
                st.info("No Balance Sheet concepts found in this filing.")
            else:
                st.dataframe(bs_df, use_container_width=True)

                buf = BytesIO()
                bs_df.to_excel(buf, index=False, engine="openpyxl")
                buf.seek(0)

                st.download_button(
                    "⬇ Download Balance Sheet",
                    data=buf,
                    file_name=f"xbrl_bs_{item['index']}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # ---------------- FULL FACTS TAB ----------------

        with tab_all:

            st.dataframe(df.head(200), use_container_width=True)

            buf = BytesIO()
            df.to_excel(buf, index=False, engine="openpyxl")
            buf.seek(0)

            st.download_button(
                "⬇ Download full fact table",
                data=buf,
                file_name=f"xbrl_all_{item['index']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
