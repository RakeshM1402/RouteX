import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "routex_star_schema_architecture.png"

# Setup high-res figure
fig, ax = plt.subplots(figsize=(18, 12), dpi=300)
ax.set_xlim(0, 18)
ax.set_ylim(0, 12)
ax.axis('off')
fig.patch.set_facecolor('#0F172A') # Dark slate modern theme

def draw_card(ax, x, y, w, h, title, subtitle, items, bg_color, header_color, border_color):
    # Base card
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15",
                                  facecolor=bg_color, edgecolor=border_color, linewidth=2)
    ax.add_patch(rect)
    
    # Header box
    h_h = 0.9
    header_rect = patches.FancyBboxPatch((x, y + h - h_h), w, h_h, boxstyle="round,pad=0.02,rounding_size=0.15",
                                         facecolor=header_color, edgecolor=border_color, linewidth=1.5)
    ax.add_patch(header_rect)
    
    # Title & Tag
    ax.text(x + 0.3, y + h - 0.35, title, fontsize=10.5, weight='bold', color='#FFFFFF', va='center')
    ax.text(x + w - 0.3, y + h - 0.35, subtitle, fontsize=8, weight='bold', color='#38BDF8', va='center', ha='right')
    
    # Field list
    curr_y = y + h - 1.2
    for item in items:
        prefix = item.get('prefix', '')
        name = item.get('name', '')
        dtype = item.get('type', '')
        pcolor = item.get('pcolor', '#94A3B8')
        
        if prefix:
            ax.text(x + 0.3, curr_y, prefix, fontsize=7.5, weight='bold', color=pcolor, va='center')
        ax.text(x + 0.8, curr_y, name, fontsize=8.2, weight='medium', color='#F1F5F9', va='center')
        ax.text(x + w - 0.3, curr_y, dtype, fontsize=7.5, color='#94A3B8', va='center', ha='right')
        curr_y -= 0.32

# ==================== DIMENSION TABLES (Outer Ring) ====================
dim_style = dict(bg_color='#1E293B', header_color='#0369A1', border_color='#38BDF8')

# 1. dim_geography (Left Top)
draw_card(ax, 0.8, 6.2, 4.4, 4.5, "dim_geography", "DIMENSION", [
    {'prefix': 'PK', 'name': 'geography_key', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': ' ', 'name': 'state_name', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'state_code', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'region', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'population', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'area_sq_km', 'type': 'REAL', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'population_density', 'type': 'REAL', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'density_tier', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'districts_count', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'centroid_latitude', 'type': 'REAL', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'centroid_longitude', 'type': 'REAL', 'pcolor': '#94A3B8'},
], **dim_style)

# 2. dim_time (Right Top)
draw_card(ax, 12.8, 6.7, 4.4, 3.8, "dim_time", "DIMENSION", [
    {'prefix': 'PK', 'name': 'time_key', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': ' ', 'name': 'year', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'quarter', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'month_number', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'month_name', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'season', 'type': 'TEXT', 'pcolor': '#94A3B8'},
], **dim_style)

# 3. dim_diurnal (Left Bottom)
draw_card(ax, 0.8, 1.2, 4.4, 3.4, "dim_diurnal", "DIMENSION", [
    {'prefix': 'PK', 'name': 'diurnal_key', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': ' ', 'name': 'time_slot', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'period', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'start_hour', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'end_hour', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
], **dim_style)

# 4. dim_highway (Right Bottom)
draw_card(ax, 12.8, 1.2, 4.4, 3.8, "dim_highway", "DIMENSION", [
    {'prefix': 'PK', 'name': 'highway_key', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': ' ', 'name': 'highway_name', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'road_type', 'type': 'TEXT', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'segment_count', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'total_length_km', 'type': 'REAL', 'pcolor': '#94A3B8'},
    {'prefix': ' ', 'name': 'corridor_tier', 'type': 'TEXT', 'pcolor': '#94A3B8'},
], **dim_style)


# ==================== FACT TABLES (Central Star Hub) ====================
fact_style = dict(bg_color='#1E293B', header_color='#B45309', border_color='#F59E0B')

# Fact 1: Monthly (Center Top)
draw_card(ax, 6.7, 7.5, 4.6, 3.0, "fact_monthly_accidents", "FACT TABLE", [
    {'prefix': 'PK', 'name': 'fact_id', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': 'FK', 'name': 'geography_key', 'type': 'INTEGER', 'pcolor': '#EC4899'},
    {'prefix': 'FK', 'name': 'time_key', 'type': 'INTEGER', 'pcolor': '#EC4899'},
    {'prefix': 'M',  'name': 'accidents_count', 'type': 'INTEGER', 'pcolor': '#10B981'},
], **fact_style)

# Fact 2: Diurnal (Center Middle)
draw_card(ax, 6.7, 4.1, 4.6, 3.2, "fact_diurnal_accidents", "FACT TABLE", [
    {'prefix': 'PK', 'name': 'fact_id', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': 'FK', 'name': 'geography_key', 'type': 'INTEGER', 'pcolor': '#EC4899'},
    {'prefix': 'FK', 'name': 'diurnal_key', 'type': 'INTEGER', 'pcolor': '#EC4899'},
    {'prefix': ' ',  'name': 'year', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': 'M',  'name': 'accidents_count', 'type': 'INTEGER', 'pcolor': '#10B981'},
    {'prefix': 'M',  'name': 'share_of_annual_total_pct', 'type': 'REAL', 'pcolor': '#10B981'},
], **fact_style)

# Fact 3: Annual Safety (Center Bottom)
draw_card(ax, 6.7, 0.4, 4.6, 3.5, "fact_annual_safety", "FACT TABLE", [
    {'prefix': 'PK', 'name': 'fact_id', 'type': 'INTEGER', 'pcolor': '#FACC15'},
    {'prefix': 'FK', 'name': 'geography_key', 'type': 'INTEGER', 'pcolor': '#EC4899'},
    {'prefix': ' ',  'name': 'year', 'type': 'INTEGER', 'pcolor': '#94A3B8'},
    {'prefix': 'M',  'name': 'fatalities', 'type': 'INTEGER', 'pcolor': '#10B981'},
    {'prefix': 'M',  'name': 'total_accidents', 'type': 'INTEGER', 'pcolor': '#10B981'},
    {'prefix': 'M',  'name': 'fatalities_per_lakh', 'type': 'REAL', 'pcolor': '#10B981'},
    {'prefix': 'M',  'name': 'severity_index', 'type': 'REAL', 'pcolor': '#10B981'},
], **fact_style)

# ==================== CONNECTOR LINES (FK -> PK) ====================
connector_props = dict(arrowstyle="->", color="#38BDF8", lw=1.8, mutation_scale=14, linestyle="--")

# dim_geography -> fact_monthly_accidents
ax.annotate("", xy=(6.7, 8.8), xytext=(5.2, 8.8), arrowprops=connector_props)
# dim_geography -> fact_diurnal_accidents
ax.annotate("", xy=(6.7, 5.8), xytext=(5.2, 7.5), arrowprops=connector_props)
# dim_geography -> fact_annual_safety
ax.annotate("", xy=(6.7, 2.2), xytext=(5.2, 6.8), arrowprops=connector_props)

# dim_time -> fact_monthly_accidents
ax.annotate("", xy=(11.3, 8.8), xytext=(12.8, 8.8), arrowprops=dict(arrowstyle="->", color="#38BDF8", lw=1.8, mutation_scale=14, linestyle="--"))

# dim_diurnal -> fact_diurnal_accidents
ax.annotate("", xy=(6.7, 5.0), xytext=(5.2, 3.0), arrowprops=dict(arrowstyle="->", color="#38BDF8", lw=1.8, mutation_scale=14, linestyle="--"))

# Title & Legend Header
ax.text(9.0, 11.5, "RouteX Intelligent Safety & Analytics — Star Schema Architecture", 
        fontsize=16, weight='bold', color='#FFFFFF', ha='center')
ax.text(9.0, 11.1, "Data Warehouse Dimensional Model: Central Fact Hub with Fully Denormalized Radial Dimensions", 
        fontsize=10.5, color='#94A3B8', ha='center')

# Legend at bottom right/left
leg_x, leg_y = 0.8, 0.4
ax.text(leg_x, leg_y + 0.3, "SCHEMA CONVENTIONS:", fontsize=8.5, weight='bold', color='#E2E8F0')
ax.text(leg_x, leg_y, "PK = Primary Key", fontsize=8, color='#FACC15', weight='bold')
ax.text(leg_x + 2.0, leg_y, "FK = Foreign Key", fontsize=8, color='#EC4899', weight='bold')
ax.text(leg_x + 4.0, leg_y, "M = Additive/Semi-Additive Measure", fontsize=8, color='#10B981', weight='bold')

plt.tight_layout()
plt.savefig(OUT, facecolor=fig.get_facecolor(), edgecolor='none', bbox_inches='tight')
plt.close()
print("Saved publication-quality diagram to:", OUT)
