import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "schema_star_diagram.png"

fig, ax = plt.subplots(figsize=(14, 10))
ax.set_xlim(0, 14)
ax.set_ylim(0, 10)
ax.axis('off')

# Colors
fact_color = '#FFE5B4'
dim_color = '#B4D7FF'
cube_color = '#D4F8D4'
border = '#333333'

# Center facts
facts = [
    (7, 5, 'fact_monthly_accidents\n(geography_key, time_key,\naccidents_count)'),
    (5, 6.5, 'fact_diurnal_accidents\n(geography_key, year,\ndiurnal_key, accidents_count,\nshare_of_annual_total_pct)'),
    (9, 6.5, 'fact_annual_safety\n(geography_key, year,\nfatalities, total_accidents,\nfatalities_per_lakh,\nseverity_index, fatality_rank,\nsafety_risk_tier)'),
]

for x,y,text in facts:
    ax.add_patch(patches.FancyBboxPatch((x-1.2,y-0.6), 2.4, 1.2, boxstyle="round,pad=0.02", 
                                       facecolor=fact_color, edgecolor=border, linewidth=2))
    ax.text(x,y,text, ha='center', va='center', fontsize=8, weight='bold')

# Dimensions
dims = [
    (7, 2.5, 'dim_geography\n(geography_key PK,\nstate_name, region,\npopulation, density_tier, ...)'),
    (4, 3.5, 'dim_time\n(time_key PK,\nyear, month, quarter,\nseason)'),
    (10, 3.5, 'dim_diurnal\n(diurnal_key PK,\ntime_slot, period,\nstart_hour, end_hour)'),
    (7, 8, 'dim_highway\n(highway_key PK,\nhighway_name, road_type,\nsegment_count, total_length_km,\ncorridor_tier)'),
]

for x,y,text in dims:
    ax.add_patch(patches.FancyBboxPatch((x-1.1,y-0.7), 2.2, 1.4, boxstyle="round,pad=0.02",
                                       facecolor=dim_color, edgecolor=border, linewidth=2))
    ax.text(x,y,text, ha='center', va='center', fontsize=8)

# Lines from facts to dims
# monthly to geography and time
ax.plot([7,7],[4.4,2.9], color=border, lw=1.5)
ax.plot([5.8,4.6],[5.4,4.0], color=border, lw=1.5)
# diurnal to geography and diurnal
ax.plot([5.6,4.9],[6.2,4.0], color=border, lw=1.5)
ax.plot([5.8,6.1] if False else [5.9,9.5-0.5],[6.8,4.2], color=border, lw=1.5) # rough
ax.plot([6.2,9.0],[6.5,4.2], color=border, lw=1.5)
# annual to geography
ax.plot([8.2,7.8],[6.2,3.2], color=border, lw=1.5)

# Label connections
ax.text(7, 3.6, 'FK', ha='center', va='center', fontsize=7, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
ax.text(4.8, 4.8, 'FK', ha='center', va='center', fontsize=7, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
ax.text(9.2, 4.8, 'FK', ha='center', va='center', fontsize=7, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
ax.text(7.8, 4.4, 'FK', ha='center', va='center', fontsize=7, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

# Cubes
cubes = [
    (2, 7.5, 'cube_temporal_seasonality'),
    (2, 6.5, 'cube_diurnal_risk'),
    (12, 7.5, 'cube_state_safety_measures'),
    (12, 6.5, 'cube_regional_demographics'),
]
for x,y,text in cubes:
    ax.add_patch(patches.FancyBboxPatch((x-1,y-0.25), 2, 0.5, boxstyle="round,pad=0.01",
                                       facecolor=cube_color, edgecolor=border))
    ax.text(x,y,text, ha='center', va='center', fontsize=7)

ax.text(7, 9.2, 'RouteX OLAP - Star Schema', ha='center', va='center', fontsize=16, weight='bold')
ax.text(7, 8.8, 'Facts (center) connected directly to Dimensions (denormalized)', ha='center', va='center', fontsize=10)

plt.tight_layout()
plt.savefig(OUT, dpi=200, bbox_inches='tight')
plt.close()
print('saved:', OUT)
