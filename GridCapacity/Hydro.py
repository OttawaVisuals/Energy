import requests, json, time

BASE = "https://gis.planview.ca/server/rest/services/OEB/OEB_Available_Capacity/FeatureServer/0"
QUERY = BASE + "/query"
HEADERS = {
    "Referer": "https://gis.planview.ca/portal/apps/experiencebuilder/experience/?id=81261dc17514429da65fbf52feca4c2e",
    "Origin": "https://gis.planview.ca",
    "User-Agent": "Mozilla/5.0",
}
WHERE = "ldc_name LIKE '%Ottawa%'"   # tighten after you see the distinct names below

def get(params):
    r = requests.get(QUERY, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()

# max page size the server allows
meta = requests.get(BASE, params={"f": "json"}, headers=HEADERS).json()
page = meta.get("maxRecordCount", 1000)
print("maxRecordCount:", page)

# what actually matches "Ottawa"
distinct = get({"where": WHERE, "outFields": "ldc_name",
                "returnDistinctValues": "true", "returnGeometry": "false", "f": "json"})
print("Matching LDC names:", [f["attributes"]["ldc_name"] for f in distinct["features"]])

# total count for the filter
count = get({"where": WHERE, "returnCountOnly": "true", "f": "json"})["count"]
print("Ottawa records:", count)

# paged pull
features, offset = [], 0
while True:
    data = get({"where": WHERE, "outFields": "*", "returnGeometry": "true",
                "outSR": "4326", "f": "geojson",
                "resultOffset": offset, "resultRecordCount": page})
    batch = data.get("features", [])
    features.extend(batch)
    print(f"  fetched {len(features)}/{count}")
    if len(batch) < page:
        break
    offset += page
    time.sleep(0.2)

out = {"type": "FeatureCollection", "features": features}
with open("ottawa_capacity.geojson", "w", encoding="utf-8") as f:
    json.dump(out, f)
print("Wrote ottawa_capacity.geojson —", len(features), "features")