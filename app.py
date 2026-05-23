"""
Apollo Medicines Flask API
Serves medicine data from apollo.csv with search, filtering, and pagination.
"""

import re
import math
import pandas as pd
try:
    from flask import Flask, jsonify, request, abort  # type: ignore
except ImportError:
    raise ImportError("Flask is not installed. Please install it using: pip install flask pandas")

app = Flask(__name__)

# ── Load & clean data once at startup ─────────────────────────────────────────

CSV_PATH = r"C:\Users\kittu\OneDrive\Desktop\api call\apollo.csv"

df_raw = pd.read_csv(CSV_PATH)

# Collect array-style columns (e.g. category_tags[0], search_aliases[1], …)
def collect_array_cols(df, prefix):
    cols = sorted(
        [c for c in df.columns if re.match(rf"^{re.escape(prefix)}\[\d+\]$", c)],
        key=lambda c: int(re.search(r"\[(\d+)\]", c).group(1)),
    )
    return (
        df[cols]
        .apply(lambda row: [v for v in row if pd.notna(v) and v != ""], axis=1)
        .tolist()
    )

def collect_dosage_components(df):
    value_cols = sorted(
        [c for c in df.columns if re.match(r"^dosage_components\[\d+\]\.value$", c)],
        key=lambda c: int(re.search(r"\[(\d+)\]", c).group(1)),
    )
    unit_cols = sorted(
        [c for c in df.columns if re.match(r"^dosage_components\[\d+\]\.unit$", c)],
        key=lambda c: int(re.search(r"\[(\d+)\]", c).group(1)),
    )
    components = []
    for _, row in df.iterrows():
        pairs = []
        for v_col, u_col in zip(value_cols, unit_cols):
            v, u = row.get(v_col), row.get(u_col)
            if pd.notna(v) and v != "":
                pairs.append({"value": v, "unit": u if pd.notna(u) else None})
        components.append(pairs)
    return components


def build_records(df):
    records = []
    cat_tags      = collect_array_cols(df, "category_tags")
    search_aliases = collect_array_cols(df, "search_aliases")
    brand_tokens  = collect_array_cols(df, "brand_tokens")
    comp_salts    = collect_array_cols(df, "composition_salts")
    dosage_comps  = collect_dosage_components(df)

    pack_fields = [
        "pack_size_raw", "pack_size_value", "pack_size_unit",
        "packing_type", "packing_size_description",
        "sellable_unit", "units_per_sellable", "sellable_unit_type",
    ]

    def v(row, col):
        val = row.get(col)
        return None if pd.isna(val) else val

    for i, (_, row) in enumerate(df.iterrows()):
        pack = {f: v(row, f"pack_size.{f}") for f in pack_fields}

        records.append({
            "id":                 v(row, "_id"),
            "medicine_name":      v(row, "medicine_name"),
            "brand":              v(row, "brand"),
            "brand_normalized":   v(row, "brand_normalized"),
            "manufacturer":       v(row, "manufacturer") or v(row, "manufacturer_name"),
            "form":               v(row, "form"),
            "form_group":         v(row, "form_group"),
            "dosage":             v(row, "dosage"),
            "dosage_unit":        v(row, "dosage_unit"),
            "dosage_value":       v(row, "dosage_value"),
            "dosage_pattern":     v(row, "dosage_pattern"),
            "dosage_components":  dosage_comps[i],
            "composition":        v(row, "composition"),
            "normalized_composition": v(row, "normalized_composition"),
            "composition_salts":  comp_salts[i],
            "schedule":           v(row, "schedule"),
            "item_category":      v(row, "item_category"),
            "item_type":          v(row, "item_type"),
            "primary_benefit":    v(row, "primary_benefit"),
            "primary_category_id": v(row, "primary_category_id"),
            "category_tags":      cat_tags[i],
            "search_aliases":     search_aliases[i],
            "brand_tokens":       brand_tokens[i],
            "pack_size":          pack,
            "mrp":                v(row, "mrp"),
            "price":              v(row, "price"),
            "sale_discount":      v(row, "sale_discount"),
            "is_active":          v(row, "is_active"),
            "slug":               v(row, "slug"),
            "alternative_match_key": v(row, "alternative_match_key"),
            "created_at":         v(row, "created_at"),
            "updated_at":         v(row, "updated_at"),
        })
    return records


MEDICINES = build_records(df_raw)
print(f"✅  Loaded {len(MEDICINES)} medicines from {CSV_PATH}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def paginate(items, page, per_page):
    total   = len(items)
    pages   = math.ceil(total / per_page) if per_page else 1
    start   = (page - 1) * per_page
    end     = start + per_page
    return items[start:end], {
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    pages,
    }


def success(data, meta=None, status=200):
    body = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def error(message, status=400):
    return jsonify({"success": False, "error": message}), status


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "name":    "Apollo Medicines API",
        "version": "1.0.0",
        "total_records": len(MEDICINES),
        "endpoints": {
            "GET /medicines":              "List all medicines (paginated)",
            "GET /medicines/<id>":         "Get a single medicine by ID",
            "GET /medicines/search":       "Full-text search on name / brand / composition",
            "GET /medicines/filter":       "Filter by category, form, schedule, is_active, item_type",
            "GET /medicines/brands":       "List distinct brands",
            "GET /medicines/categories":   "List distinct category tags",
            "GET /medicines/forms":        "List distinct forms",
            "GET /medicines/stats":        "Summary statistics",
        },
    })


# -- List -------------------------------------------------------------------

@app.route("/medicines")
def list_medicines():
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        return error("page and per_page must be integers")

    items, meta = paginate(MEDICINES, page, per_page)
    return success(items, meta)


# -- Single record ----------------------------------------------------------

@app.route("/medicines/<med_id>")
def get_medicine(med_id):
    for m in MEDICINES:
        if m["id"] == med_id:
            return success(m)
    return error(f"Medicine with id '{med_id}' not found", 404)


# -- Search -----------------------------------------------------------------

@app.route("/medicines/search")
def search_medicines():
    q = request.args.get("q", "").strip().lower()
    if not q:
        return error("Query parameter 'q' is required")

    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        return error("page and per_page must be integers")

    fields = ["medicine_name", "brand", "manufacturer", "composition",
              "primary_benefit", "dosage", "schedule"]

    results = []
    for m in MEDICINES:
        for f in fields:
            val = m.get(f)
            if val and q in str(val).lower():
                results.append(m)
                break
        else:
            # also search inside list fields
            for lf in ["category_tags", "search_aliases", "composition_salts"]:
                if any(q in str(t).lower() for t in (m.get(lf) or [])):
                    results.append(m)
                    break

    items, meta = paginate(results, page, per_page)
    meta["query"] = q
    return success(items, meta)


# -- Filter -----------------------------------------------------------------

@app.route("/medicines/filter")
def filter_medicines():
    category   = request.args.get("category", "").strip().lower()
    form       = request.args.get("form", "").strip().lower()
    schedule   = request.args.get("schedule", "").strip().lower()
    item_type  = request.args.get("item_type", "").strip().lower()
    is_active  = request.args.get("is_active", "").strip().lower()

    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
    except ValueError:
        return error("page and per_page must be integers")

    results = MEDICINES

    if category:
        results = [m for m in results
                   if any(category in str(t).lower() for t in (m["category_tags"] or []))]
    if form:
        results = [m for m in results if m["form"] and form in m["form"].lower()]
    if schedule:
        results = [m for m in results if m["schedule"] and schedule in m["schedule"].lower()]
    if item_type:
        results = [m for m in results if m["item_type"] and item_type in m["item_type"].lower()]
    if is_active in ("true", "false"):
        flag = is_active == "true"
        results = [m for m in results if m["is_active"] == flag]

    if not any([category, form, schedule, item_type, is_active]):
        return error("At least one filter parameter is required: category, form, schedule, item_type, is_active")

    items, meta = paginate(results, page, per_page)
    return success(items, meta)


# -- Lookup lists -----------------------------------------------------------

@app.route("/medicines/brands")
def list_brands():
    brands = sorted({m["brand"] for m in MEDICINES if m["brand"]})
    return success(brands, {"total": len(brands)})


@app.route("/medicines/categories")
def list_categories():
    cats = set()
    for m in MEDICINES:
        for t in (m["category_tags"] or []):
            if t:
                cats.add(t)
    return success(sorted(cats), {"total": len(cats)})


@app.route("/medicines/forms")
def list_forms():
    forms = sorted({m["form"] for m in MEDICINES if m["form"]})
    return success(forms, {"total": len(forms)})


# -- Stats ------------------------------------------------------------------

@app.route("/medicines/stats")
def stats():
    total     = len(MEDICINES)
    active    = sum(1 for m in MEDICINES if m["is_active"])
    schedules = {}
    for m in MEDICINES:
        s = m["schedule"] or "Unknown"
        schedules[s] = schedules.get(s, 0) + 1

    item_types = {}
    for m in MEDICINES:
        t = m["item_type"] or "Unknown"
        item_types[t] = item_types.get(t, 0) + 1

    forms = {}
    for m in MEDICINES:
        f = m["form"] or "Unknown"
        forms[f] = forms.get(f, 0) + 1

    prices = [m["mrp"] for m in MEDICINES if m["mrp"] is not None]

    return success({
        "total_medicines":   total,
        "active_medicines":  active,
        "inactive_medicines": total - active,
        "by_schedule":       schedules,
        "by_item_type":      item_types,
        "by_form":           forms,
        "pricing": {
            "with_mrp":   len(prices),
            "min_mrp":    min(prices) if prices else None,
            "max_mrp":    max(prices) if prices else None,
            "avg_mrp":    round(sum(prices) / len(prices), 2) if prices else None,
        },
    })


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(_):
    return error("Endpoint not found", 404)

@app.errorhandler(405)
def method_not_allowed(_):
    return error("Method not allowed", 405)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
