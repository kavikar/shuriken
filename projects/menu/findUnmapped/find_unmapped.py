import argparse
import csv
import json
from typing import List

from web_server import fetch_unmapped_for_location


def parse_values(raw: str) -> List[str]:
	return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def parse_csv(path: str):
	locations = []
	products = []
	with open(path, "r", encoding="utf-8") as f:
		reader = csv.DictReader(f)
		for row in reader:
			lower = {k.lower(): (v or "").strip() for k, v in row.items()}
			loc = lower.get("location_id") or lower.get("store_id") or lower.get("location")
			prod = lower.get("product_id") or lower.get("item_id") or lower.get("product")
			if loc:
				locations.append(loc)
			if prod:
				products.append(prod)
	return sorted(set(locations)), sorted(set(products))


def run(brand: str, locations: List[str], products: List[str]):
	results = []
	for loc in locations:
		payload = fetch_unmapped_for_location(brand, loc)
		item_set = set(payload["items"])
		for prod in products:
			results.append({
				"location_id": loc,
				"product_id": prod,
				"is_unmapped": prod in item_set,
				"unmapped_count": len(item_set),
				"api_status": payload["status"],
				"http_status": payload["http_status"],
			})
	return results


def main():
	parser = argparse.ArgumentParser(description="findUnmapped CLI")
	parser.add_argument("--brand", default="B1", help="B1/B2/B3")
	parser.add_argument("--locations", default="", help="Comma/newline-separated location IDs")
	parser.add_argument("--products", default="", help="Comma/newline-separated product IDs")
	parser.add_argument("--csv", default="", help="CSV file with location_id and optional product_id")
	parser.add_argument("--out", default="", help="Optional output JSON path")
	args = parser.parse_args()

	brand = args.brand.upper().strip()
	locations = parse_values(args.locations)
	products = parse_values(args.products)

	if args.csv:
		csv_locations, csv_products = parse_csv(args.csv)
		if not locations:
			locations = csv_locations
		if not products:
			products = csv_products

	if not locations or not products:
		raise SystemExit("Provide locations and products (or CSV with those columns).")

	results = run(brand, locations, products)
	output = {
		"brand": brand,
		"locations": len(locations),
		"products": len(products),
		"total_checks": len(results),
		"unmapped": len([r for r in results if r["is_unmapped"]]),
		"results": results,
	}

	text = json.dumps(output, indent=2)
	if args.out:
		with open(args.out, "w", encoding="utf-8") as f:
			f.write(text)
		print(f"Saved results: {args.out}")
	else:
		print(text)


if __name__ == "__main__":
	main()
