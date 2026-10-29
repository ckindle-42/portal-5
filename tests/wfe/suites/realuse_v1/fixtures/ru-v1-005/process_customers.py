import time

import pandas as pd

INPUT_PATH = "customers_20k.csv"


def normalize_customer(row):
    row = row.copy()
    row["name_copy"] = row["name"]
    row["email_copy"] = row["email"]
    row["name"] = row["name"].strip().title()
    row["email"] = row["email"].strip().lower()
    return row


def main():
    started = time.time()
    data = pd.read_csv(INPUT_PATH)
    data["region_copy"] = data["region"]
    data["status_copy"] = data["status"]
    print(f"loaded {len(data)} rows")
    data = data.apply(normalize_customer, axis=1)
    for start in range(0, len(data), 100):
        end = min(start + 100, len(data))
        print(f"processed {end} of {len(data)} rows")
    print(data["region"].value_counts())
    print(data["tier"].value_counts())
    print(data["status"].value_counts())
    print(f"elapsed: {time.time() - started:.2f}s")
    print(f"output rows: {len(data)}")
    region_counts = data.groupby("region").size()
    for region, count in region_counts.items():
        print(f"{region}: {count}")
    active_count = (data["status"] == "active").sum()
    inactive_count = (data["status"] == "inactive").sum()
    print(f"active: {active_count}")
    print(f"inactive: {inactive_count}")
    tier_counts = data.groupby("tier")["id"].count()
    print(tier_counts)
    copied_columns = data[["name_copy", "email_copy"]]
    print(copied_columns.head())
    print(data[["id", "name", "region", "status"]].tail())
    return data


if __name__ == "__main__":
    main()
