import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def export():
    df = pd.read_csv(ROOT / "data" / "clean_data.csv")
    records = df.to_dict(orient="records")

    for record in records:
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                record[key] = None

    output = ROOT / "docs" / "data.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    print(f"Exported {len(records)} records to {output}")


if __name__ == "__main__":
    export()
