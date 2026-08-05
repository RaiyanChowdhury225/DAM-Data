import requests
from bs4 import BeautifulSoup

ARCHIVE_URL = "http://dam.portal.gov.bd/pages/static-pages/6922e15c933eb65569e2bb7a"

response = requests.get(ARCHIVE_URL, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

# -------------------------------------------------
# 1. How many tables are there?
# -------------------------------------------------
tables = soup.find_all("table")
print(f"\nNumber of tables: {len(tables)}")

# -------------------------------------------------
# 2. How many rows does each table have?
# -------------------------------------------------
for i, table in enumerate(tables):
    rows = table.find_all("tr")
    print(f"Table {i}: {len(rows)} rows")

# -------------------------------------------------
# 3. Print the header row of each table
# -------------------------------------------------
for i, table in enumerate(tables):
    rows = table.find_all("tr")

    if rows:
        print(f"\n===== HEADER OF TABLE {i} =====")
        print(rows[0].prettify())

# -------------------------------------------------
# 4. Print the first data row of each table
# -------------------------------------------------
for i, table in enumerate(tables):
    rows = table.find_all("tr")

    if len(rows) > 1:
        print(f"\n===== FIRST DATA ROW OF TABLE {i} =====")
        print(rows[1].prettify())

# -------------------------------------------------
# 5. Count PDF links in each table
# -------------------------------------------------
for i, table in enumerate(tables):
    pdf_links = table.find_all("a", href=True)

    pdf_count = sum(
        1
        for link in pdf_links
        if link["href"].lower().endswith(".pdf")
    )

    print(f"\nTable {i}: {pdf_count} PDF links")

# -------------------------------------------------
# 6. Show the text from the first few rows
# -------------------------------------------------
if tables:
    print("\n===== FIRST 5 ROWS (TEXT ONLY) =====")

    rows = tables[0].find_all("tr")

    for row in rows[:5]:
        cells = row.find_all(["td", "th"])
        print([cell.get_text(strip=True) for cell in cells])