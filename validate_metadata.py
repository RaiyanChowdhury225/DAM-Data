import pandas as pd
from config import METADATA_CSV


df = pd.read_csv(METADATA_CSV)


print("Total records:")
print(len(df))


print("\nMissing values:")
print(df.isna().sum())


print("\nSource distribution:")
print(df["source_page"].value_counts())


print("\nDivision distribution:")
print(df["division"].value_counts())


print("\nDuplicate PDF URLs:")
print(
    df["pdf_url"].duplicated().sum()
)