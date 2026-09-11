import json

from find_unmapped import parse_values, run


def main():
	print("findUnmapped interactive mode")
	brand = input("Brand (B1/B2/B3) [B1]: ").strip().upper() or "B1"
	locations_raw = input("Locations (comma separated): ").strip()
	products_raw = input("Products (comma separated): ").strip()

	locations = parse_values(locations_raw)
	products = parse_values(products_raw)

	if not locations or not products:
		print("Locations and products are required.")
		return

	results = run(brand, locations, products)
	summary = {
		"brand": brand,
		"total_checks": len(results),
		"unmapped": len([r for r in results if r["is_unmapped"]]),
		"results": results,
	}
	print(json.dumps(summary, indent=2))


if __name__ == "__main__":
	main()
