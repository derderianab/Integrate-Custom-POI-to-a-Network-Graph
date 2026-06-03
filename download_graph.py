import os
import osmnx as ox

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
PLACE       = "Kota Bandung, West Java, Indonesia"
OUTPUT_DIR  = "join_poi_network/data"

NETWORK_TYPE = "drive"
NETWORK_CRS  = "EPSG:32748"

AMENITIES = {
    "hospitals"    : {"amenity": "hospital"},
    "clinics"      : {"amenity": "clinic"},
    "police"       : {"amenity": "police"},
    "fire_stations": {"amenity": "fire_station"},
}

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────
# Download Road Network
# ─────────────────────────────────────────
def download_network():
    G = ox.graph_from_place(PLACE, network_type=NETWORK_TYPE)
    nodes, edges = ox.graph_to_gdfs(G)

    nodes = nodes.to_crs(NETWORK_CRS)
    edges = edges.to_crs(NETWORK_CRS)

    nodes.to_file(os.path.join(OUTPUT_DIR, "nodes.gpkg"), driver="GPKG")
    edges.to_file(os.path.join(OUTPUT_DIR, "edges.gpkg"), driver="GPKG")

    print(f"Network saved → {OUTPUT_DIR}/nodes.gpkg, edges.gpkg")


# ─────────────────────────────────────────
# Download Amenities
# ─────────────────────────────────────────
def download_amenities():
    for name, tags in AMENITIES.items():
        gdf = ox.features_from_place(PLACE, tags=tags)
        out_path = os.path.join(OUTPUT_DIR, f"{name}.gpkg")
        gdf.to_file(out_path, driver="GPKG")
        print(f"{name} saved → {out_path} ({len(gdf)} features)")


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
if __name__ == "__main__":
    # download_network()
    download_amenities()