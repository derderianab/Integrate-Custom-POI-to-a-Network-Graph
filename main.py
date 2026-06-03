import geopandas as gpd
from shapely.geometry import Point, LineString
from shapely.ops import split

# ─────────────────────────────────────────
# Config
# ─────────────────────────────────────────
POI_PATH   = r"join_poi_network/data/point_of_interest_32748.gpkg"
EDGE_PATH  = r"join_poi_network/data/kota_bandung_edges_32748.gpkg"
NODE_PATH  = r"join_poi_network/data/kota_bandung_nodes_32748.gpkg"
OUTPUT_EDGE_PATH = r"join_poi_network/output/test_updated_edges.gpkg"
OUTPUT_NODE_PATH = r"join_poi_network/output/test_updated_nodes.gpkg"

POI_ID_COL = "conn_id"
TOLERANCE  = 0.01  # meter


# ─────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────
def make_connector_edges(u_osmid, v_osmid, u_geom, v_geom, name):
    """Create bidirectional connector edges between two nodes."""
    line_out = LineString([u_geom, v_geom])
    line_in  = LineString([v_geom, u_geom])
    base = {
        "key": 0,
        "osmid": None,
        "highway": "unclassified",
        "lanes": None,
        "name": name,
        "oneway": False,
        "length": line_out.length,
        "ref": None,
        "width": None,
        "maxspeed": None,
        "access": None,
        "bridge": None,
        "junction": None,
        "tunnel": None,
        "est_width": None,
    }
    edge_out = {**base, "u": u_osmid, "v": v_osmid, "reversed": False, "geometry": line_out}
    edge_in  = {**base, "u": v_osmid, "v": u_osmid, "reversed": True,  "geometry": line_in}
    return edge_out, edge_in


def make_split_edges(nearest_edge, projected_osmid, line1, line2):
    """Create 4 replacement edges after splitting nearest_edge at projected point."""
    base = {k: nearest_edge[k] for k in [
        "key", "highway", "lanes", "name", "oneway",
        "ref", "width", "maxspeed", "access",
        "bridge", "junction", "tunnel", "est_width"
    ]}
    u_orig = nearest_edge["u"]
    v_orig = nearest_edge["v"]

    e1_out = {**base, "u": u_orig,          "v": projected_osmid, "reversed": False,
              "osmid": nearest_edge["osmid"] + "_1_out", "length": line1.length, "geometry": line1}
    e1_in  = {**base, "u": projected_osmid, "v": u_orig,          "reversed": True,
              "osmid": nearest_edge["osmid"] + "_1_in",  "length": line1.length, "geometry": LineString(list(line1.coords)[::-1])}
    e2_out = {**base, "u": projected_osmid, "v": v_orig,          "reversed": False,
              "osmid": nearest_edge["osmid"] + "_2_out", "length": line2.length, "geometry": line2}
    e2_in  = {**base, "u": v_orig,          "v": projected_osmid, "reversed": True,
              "osmid": nearest_edge["osmid"] + "_2_in",  "length": line2.length, "geometry": LineString(list(line2.coords)[::-1])}

    return e1_out, e1_in, e2_out, e2_in


def append_edges(edge_gdf, *edges):
    for edge in edges:
        edge_gdf.loc[len(edge_gdf)] = edge


def drop_original_edge(edge_gdf, u_orig, v_orig):
    """Drop both directions of the original edge before split."""
    idx = edge_gdf[
        ((edge_gdf["u"] == u_orig) & (edge_gdf["v"] == v_orig)) |
        ((edge_gdf["u"] == v_orig) & (edge_gdf["v"] == u_orig))
    ].index.tolist()
    edge_gdf.drop(index=idx, inplace=True)
    edge_gdf.reset_index(drop=True, inplace=True)


# ─────────────────────────────────────────
# Load Data
# ─────────────────────────────────────────
poi_gdf  = gpd.read_file(POI_PATH)
edge_gdf = gpd.read_file(EDGE_PATH)
node_gdf = gpd.read_file(NODE_PATH)

original_crs = edge_gdf.crs


# ─────────────────────────────────────────
# Main Loop
# ─────────────────────────────────────────
for idx, row in poi_gdf.iterrows():

    edge_index = edge_gdf.sindex
    poi_geom   = row.geometry
    poi_osmid  = row[POI_ID_COL]
    poi_name   = row["name"]

    # Add existing POI as node
    node_gdf.loc[len(node_gdf)] = {
        "osmid": poi_osmid,
        "y": poi_geom.y,
        "x": poi_geom.x,
        "junction": None,
        "street_count": None,
        "highway": None,
        "ref": poi_name,
        "geometry": poi_geom
    }

    # Locate nearest edge
    nearest_idx  = edge_index.nearest(poi_geom, return_all=False)[1][0]
    nearest_edge = edge_gdf.iloc[nearest_idx]
    edge_geom    = nearest_edge.geometry

    # Project POI onto nearest edge
    projected_poi_geom = edge_geom.interpolate(edge_geom.project(poi_geom))

    # Check if projected point falls on existing node
    start_point    = Point(edge_geom.coords[0])
    end_point      = Point(edge_geom.coords[-1])
    split_required = True

    if projected_poi_geom.distance(start_point) < TOLERANCE:
        print(f"[{poi_name}] Projected → start node")
        projection_node_id   = nearest_edge["u"]
        projection_node_geom = node_gdf.loc[node_gdf["osmid"] == projection_node_id, "geometry"].values[0]
        split_required       = False

    elif projected_poi_geom.distance(end_point) < TOLERANCE:
        print(f"[{poi_name}] Projected → end node")
        projection_node_id   = nearest_edge["v"]
        projection_node_geom = node_gdf.loc[node_gdf["osmid"] == projection_node_id, "geometry"].values[0]
        split_required       = False

    # ── Case A: No split needed ──────────────────────────────────────
    if not split_required:
        edge_out, edge_in = make_connector_edges(
            u_osmid = poi_osmid,
            v_osmid = projection_node_id,
            u_geom  = poi_geom,
            v_geom  = projection_node_geom,
            name    = poi_name + "_connector"
        )
        append_edges(edge_gdf, edge_out, edge_in)

    # ── Case B: Split needed ─────────────────────────────────────────
    else:
        # Build splitter line through projected point
        dx = projected_poi_geom.x - poi_geom.x
        dy = projected_poi_geom.y - poi_geom.y
        splitter_line = LineString([
            (poi_geom.x, poi_geom.y),
            (poi_geom.x + 2 * dx, poi_geom.y + 2 * dy)
        ])

        new_edges = list(split(edge_geom, splitter_line).geoms)
        line1, line2 = new_edges[0], new_edges[1]

        # Projected POI node at split point
        projected_poi_geom = Point(line2.coords[0])
        projected_osmid    = poi_osmid + 100000

        node_gdf.loc[len(node_gdf)] = {
            "osmid": projected_osmid,
            "y": projected_poi_geom.y,
            "x": projected_poi_geom.x,
            "junction": None,
            "street_count": None,
            "highway": None,
            "ref": poi_name + "_projected",
            "geometry": projected_poi_geom
        }

        # Save drop targets before adding new edges
        u_orig = nearest_edge["u"]
        v_orig = nearest_edge["v"]

        # Add 4 split edges + 2 connector edges
        append_edges(edge_gdf, *make_split_edges(nearest_edge, projected_osmid, line1, line2))
        drop_original_edge(edge_gdf, u_orig, v_orig)

        edge_out, edge_in = make_connector_edges(
            u_osmid = poi_osmid,
            v_osmid = projected_osmid,
            u_geom  = poi_geom,
            v_geom  = projected_poi_geom,
            name    = poi_name + "_connector"
        )
        append_edges(edge_gdf, edge_out, edge_in)


# ─────────────────────────────────────────
# Export
# ─────────────────────────────────────────
edge_gdf = gpd.GeoDataFrame(edge_gdf, geometry="geometry", crs=original_crs)
node_gdf = gpd.GeoDataFrame(node_gdf, geometry="geometry", crs=original_crs)

edge_gdf.to_file(OUTPUT_EDGE_PATH, driver="GPKG")
node_gdf.to_file(OUTPUT_NODE_PATH, driver="GPKG")

print("Export complete.")
