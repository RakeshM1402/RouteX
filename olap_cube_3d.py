"""
RouteX 3D OLAP Cube Visualizer
Renders publication-quality 3D visualizations of the RouteX multidimensional
data warehouse (final dataset/routex_olap.db).

Views
-----
bars     : Year x Month x Accidents bar cube, colored by meteorological season
regional : Region x Season x Accidents slice (2001-2014 aggregate)
voxel    : Region x Season x Year-band data cube, colored by accident intensity

Usage
-----
python "olap_cube_3d.py"                 # render all three views
python "olap_cube_3d.py" --mode bars     # render one view
python "olap_cube_3d.py" --show          # render and open interactive windows
"""

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 (registers 3d projection)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "final dataset" / "routex_olap.db"
OUT_DIR = BASE_DIR / "visuals"

# ---------------------------------------------------------------------------
# Visual system
# ---------------------------------------------------------------------------
BG = "#0e1117"
PANEL = "#151a23"
TEXT = "#e6e6e6"
MUTED = "#9aa4b2"
GRID = "#2a2f3a"

SEASON_COLORS = {
    "Winter": "#5B8FF9",
    "Pre-Monsoon/Summer": "#F6BD16",
    "Monsoon": "#5AD8A6",
    "Post-Monsoon": "#E8684A",
}
SEASON_ORDER = ["Winter", "Pre-Monsoon/Summer", "Monsoon", "Post-Monsoon"]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
REGION_ORDER = ["North", "Central", "East", "West", "South", "North-East"]


def _connect():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"OLAP database not found at {DB_PATH}. Run build_olap_cube.py first."
        )
    return sqlite3.connect(DB_PATH)


def _style_axes(ax, title, subtitle=None):
    ax.set_facecolor(BG)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.set_facecolor(PANEL)
        axis.pane.set_edgecolor(GRID)
        axis._axinfo["grid"]["color"] = (0.2, 0.2, 0.25, 0.45)
        axis._axinfo["grid"]["linewidth"] = 0.6
        axis.label.set_color(TEXT)
        axis.set_tick_params(colors=MUTED, labelsize=8)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_title(title, color=TEXT, fontsize=15, fontweight="bold", pad=18)
    if subtitle:
        ax.text2D(0.5, 0.955, subtitle, transform=ax.transAxes,
                  ha="center", va="top", color=MUTED, fontsize=9)


def _season_legend(ax, loc="upper left", bbox=(1.02, 1.0)):
    handles = [Patch(facecolor=SEASON_COLORS[s], edgecolor="none", label=s)
               for s in SEASON_ORDER]
    leg = ax.legend(handles=handles, loc=loc, bbox_to_anchor=bbox,
                    frameon=False, title="Meteorological season",
                    fontsize=9, title_fontsize=9)
    for txt in leg.get_texts():
        txt.set_color(TEXT)
    leg.get_title().set_color(MUTED)
    return leg


def _save(fig, name, show=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / name
    fig.savefig(out, dpi=170, facecolor=BG, bbox_inches="tight")
    print(f" -> Saved {out}")
    if show:
        plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
def load_monthly():
    """National monthly accidents per year: shape (years, 12)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.year, t.month_number, t.season, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        GROUP BY t.year, t.month_number
        ORDER BY t.year, t.month_number
    """)
    rows = cur.fetchall()
    conn.close()

    years = sorted({r[0] for r in rows})
    y_index = {y: i for i, y in enumerate(years)}
    values = np.zeros((len(years), 12), dtype=float)
    seasons = np.empty((len(years), 12), dtype=object)
    for year, month, season, accidents in rows:
        values[y_index[year], month - 1] = accidents
        seasons[y_index[year], month - 1] = season
    return years, values, seasons


def load_regional():
    """Region x season accident totals (2001-2014)."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT g.region, t.season, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.region, t.season
    """)
    rows = cur.fetchall()
    conn.close()

    regions = [r for r in REGION_ORDER if any(row[0] == r for row in rows)]
    values = np.zeros((len(regions), len(SEASON_ORDER)), dtype=float)
    r_index = {r: i for i, r in enumerate(regions)}
    s_index = {s: i for i, s in enumerate(SEASON_ORDER)}
    for region, season, accidents in rows:
        if region in r_index and season in s_index:
            values[r_index[region], s_index[season]] = accidents
    return regions, values


def load_voxel():
    """Region x season x year-band accident totals."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT g.region, t.season, t.year, SUM(f.accidents_count) AS accidents
        FROM fact_monthly_accidents f
        JOIN dim_time t ON f.time_key = t.time_key
        JOIN dim_geography g ON f.geography_key = g.geography_key
        GROUP BY g.region, t.season, t.year
    """)
    rows = cur.fetchall()
    conn.close()

    bands = [(2001, 2004), (2005, 2008), (2009, 2011), (2012, 2014)]
    band_labels = [f"{a}-{b}" for a, b in bands]
    regions = [r for r in REGION_ORDER if any(row[0] == r for row in rows)]

    values = np.zeros((len(regions), len(SEASON_ORDER), len(bands)), dtype=float)
    r_index = {r: i for i, r in enumerate(regions)}
    s_index = {s: i for i, s in enumerate(SEASON_ORDER)}

    def band_index(year):
        for i, (a, b) in enumerate(bands):
            if a <= year <= b:
                return i
        return None

    for region, season, year, accidents in rows:
        ri = r_index.get(region)
        si = s_index.get(season)
        bi = band_index(year)
        if ri is not None and si is not None and bi is not None:
            values[ri, si, bi] += accidents
    return regions, band_labels, values


# ---------------------------------------------------------------------------
# View 1: Year x Month bar cube
# ---------------------------------------------------------------------------
def render_bars(show=False):
    years, values, seasons = load_monthly()

    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")
    _style_axes(
        ax,
        "RouteX OLAP Cube - National Road Accidents",
        "Measure: accident count  |  Axes: Year x Month x Accidents  |  Color: season",
    )

    nx, ny = values.shape
    xpos, ypos = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    xpos = xpos.ravel()
    ypos = ypos.ravel()
    zpos = np.zeros_like(xpos, dtype=float)
    dx = np.full_like(xpos, 0.72, dtype=float)
    dy = np.full_like(ypos, 0.72, dtype=float)
    dz = values.ravel()

    colors = [SEASON_COLORS.get(s, "#9aa4b2") for s in seasons.ravel()]
    ax.bar3d(xpos, ypos, zpos, dx, dy, dz,
             color=colors, alpha=0.88, shade=True, edgecolor="none")

    ax.set_xticks(np.arange(nx) + 0.36)
    ax.set_xticklabels([str(y) for y in years], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(ny) + 0.36)
    ax.set_yticklabels(MONTHS, fontsize=8)
    ax.set_xlabel("Year", labelpad=12, fontsize=10)
    ax.set_ylabel("Month", labelpad=12, fontsize=10)
    ax.set_zlabel("Accidents", labelpad=12, fontsize=10)
    ax.set_zlim(0, float(values.max()) * 1.08)
    ax.set_box_aspect((nx, ny, 9))
    ax.view_init(elev=27, azim=-125)
    _season_legend(ax)

    _save(fig, "olap_cube_3d_bars.png", show)


# ---------------------------------------------------------------------------
# View 2: Region x Season slice
# ---------------------------------------------------------------------------
def render_regional(show=False):
    regions, values = load_regional()

    fig = plt.figure(figsize=(15, 10), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")
    _style_axes(
        ax,
        "RouteX OLAP Cube Slice - Region x Season",
        "Measure: total accidents (2001-2014)  |  Slice: all regions and seasons",
    )

    nx, ny = values.shape
    xpos, ypos = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
    xpos = xpos.ravel()
    ypos = ypos.ravel()
    zpos = np.zeros_like(xpos, dtype=float)
    dx = np.full_like(xpos, 0.66, dtype=float)
    dy = np.full_like(ypos, 0.66, dtype=float)
    dz = values.ravel()

    colors = [SEASON_COLORS[s] for _ in range(nx) for s in SEASON_ORDER]
    ax.bar3d(xpos, ypos, zpos, dx, dy, dz,
             color=colors, alpha=0.9, shade=True, edgecolor="none")

    ax.set_xticks(np.arange(nx) + 0.33)
    ax.set_xticklabels(regions, rotation=25, ha="right", fontsize=9)
    ax.set_yticks(np.arange(ny) + 0.33)
    ax.set_yticklabels(SEASON_ORDER, fontsize=9)
    ax.set_xlabel("Region", labelpad=12, fontsize=10)
    ax.set_ylabel("Season", labelpad=12, fontsize=10)
    ax.set_zlabel("Accidents", labelpad=12, fontsize=10)
    ax.set_zlim(0, float(values.max()) * 1.08)
    ax.set_box_aspect((nx, ny, 7))
    ax.view_init(elev=26, azim=-128)
    _season_legend(ax)

    _save(fig, "olap_cube_3d_regional.png", show)


# ---------------------------------------------------------------------------
# View 3: Region x Season x Year-band voxel cube
# ---------------------------------------------------------------------------
def render_voxel(show=False):
    regions, band_labels, values = load_voxel()

    nx, ny, nz = values.shape
    filled = np.ones_like(values, dtype=bool)
    norm = Normalize(vmin=float(values.min()), vmax=float(values.max()))
    facecolors = cm.plasma(norm(values))
    facecolors[..., 3] = 0.92

    fig = plt.figure(figsize=(15, 11), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d")
    _style_axes(
        ax,
        "RouteX OLAP Data Cube - Region x Season x Era",
        "Voxel color: aggregate accidents  |  Cube volume: 6 regions x 4 seasons x 4 year bands",
    )

    ax.voxels(filled, facecolors=facecolors, edgecolors="#11151d", linewidth=0.25)

    ax.set_xticks(np.arange(nx) + 0.5)
    ax.set_xticklabels(regions, rotation=25, ha="right", fontsize=8)
    ax.set_yticks(np.arange(ny) + 0.5)
    ax.set_yticklabels(SEASON_ORDER, fontsize=8)
    ax.set_zticks(np.arange(nz) + 0.5)
    ax.set_zticklabels(band_labels, fontsize=8)
    ax.set_xlabel("Region", labelpad=12, fontsize=10)
    ax.set_ylabel("Season", labelpad=12, fontsize=10)
    ax.set_zlabel("Year band", labelpad=12, fontsize=10)
    ax.set_box_aspect((nx, ny, nz))
    ax.view_init(elev=24, azim=-130)

    mappable = cm.ScalarMappable(norm=norm, cmap=cm.plasma)
    mappable.set_array(values)
    cbar = fig.colorbar(mappable, ax=ax, shrink=0.6, pad=0.08, aspect=24)
    cbar.set_label("Total accidents", color=TEXT)
    cbar.ax.tick_params(colors=MUTED, labelsize=8)
    cbar.outline.set_edgecolor(GRID)

    _save(fig, "olap_cube_3d_voxel.png", show)


def main():
    parser = argparse.ArgumentParser(description="RouteX 3D OLAP cube visualizer")
    parser.add_argument("--mode", choices=["bars", "regional", "voxel", "all"],
                        default="all", help="which 3D view to render")
    parser.add_argument("--show", action="store_true",
                        help="open interactive matplotlib windows")
    args = parser.parse_args()

    modes = ["bars", "regional", "voxel"] if args.mode == "all" else [args.mode]
    renderers = {
        "bars": render_bars,
        "regional": render_regional,
        "voxel": render_voxel,
    }

    for mode in modes:
        print(f"Rendering 3D OLAP view: {mode}")
        renderers[mode](show=args.show)

    print(f"\nAll 3D OLAP visuals written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
