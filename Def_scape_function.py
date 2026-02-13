def scrape_screener_financials_by_name(company_name):

    company_url = find_screener_company_by_name(company_name)

    if not company_url:
        return None, {}

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

        name = table.find_previous(["h2", "h3"])

        key = f"Table {idx}"
        if name:
            key = name.get_text(strip=True)

        base_key = key
        count = 1
        while key in result:
            count += 1
            key = f"{base_key} ({count})"

        result[key] = df

    return company_url, result
