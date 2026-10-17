#!/usr/bin/env python3
"""Write software/schemas/*.json (JSON Schema 2020-12) from backend/schemas.py.
Run after any schema change; the frontend/agent regenerate TS types with
`npx json-schema-to-typescript software/schemas/<name>.json`."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import TypeAdapter
from backend.schemas import ALL_SCHEMAS, SCHEMA_VERSION

OUT = Path(__file__).resolve().parents[1] / "schemas"
OUT.mkdir(exist_ok=True)
index = {"version": SCHEMA_VERSION, "schemas": {}}
for name, model in ALL_SCHEMAS.items():
    schema = TypeAdapter(model).json_schema(mode="serialization")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = name
    (OUT / f"{name}.json").write_text(json.dumps(schema, indent=1) + "\n")
    index["schemas"][name] = f"{name}.json"
(OUT / "index.json").write_text(json.dumps(index, indent=1) + "\n")
print(f"wrote {len(ALL_SCHEMAS)} schemas to {OUT}")
