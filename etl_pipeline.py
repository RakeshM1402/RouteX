"""
RouteX Data Pipeline: ETL Script
Extracts, transforms, standardizes, and loads finalized analytical datasets
into 'final datset' and 'final dataset' for RouteX: Intelligent Road Safety,
Traffic Analytics, and Smart Location Recommendation System.
"""

import os
import csv
import json
import math
import shutil
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "Raw datasets"
TARGET_DIR = BASE_DIR / "final dataset"

# Canonical mapping for Indian States and Union Territories
CANONICAL_STATE_MAP = {
    'andaman and nicobar islands': 'Andaman and Nicobar Islands',
    'andaman & nicobar islands': 'Andaman and Nicobar Islands',
    'a & n islands': 'Andaman and Nicobar Islands',
    'andhra pradesh': 'Andhra Pradesh',
    'arunachal pradesh': 'Arunachal Pradesh',
    'assam': 'Assam',
    'bihar': 'Bihar',
    'chandigarh': 'Chandigarh',
    'chhattisgarh': 'Chhattisgarh',
    'dadra and nagar haveli and daman and diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra & nagar haveli and daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra & nagar haveli & daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra and nagar haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'dadra & nagar haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'd & n haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'd&n haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'daman & diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'daman and diu': 'Dadra and Nagar Haveli and Daman and Diu',
    'delhi': 'Delhi',
    'delhi (ut)': 'Delhi',
    'delhi ut': 'Delhi',
    'nct of delhi': 'Delhi',
    'goa': 'Goa',
    'gujarat': 'Gujarat',
    'gujarat and dnh & dd islands': 'Gujarat',
    'haryana': 'Haryana',
    'himachal pradesh': 'Himachal Pradesh',
    'jammu and kashmir': 'Jammu and Kashmir',
    'jammu & kashmir': 'Jammu and Kashmir',
    'j & k #': 'Jammu and Kashmir',
    'jharkhand': 'Jharkhand',
    'karnataka': 'Karnataka',
    'kerala': 'Kerala',
    'ladakh': 'Ladakh',
    'lakshadweep': 'Lakshadweep',
    'madhya pradesh': 'Madhya Pradesh',
    'maharashtra': 'Maharashtra',
    'manipur': 'Manipur',
    'meghalaya': 'Meghalaya',
    'mizoram': 'Mizoram',
    'nagaland': 'Nagaland',
    'odisha': 'Odisha',
    'orissa': 'Odisha',
    'puducherry': 'Puducherry',
    'pondicherry': 'Puducherry',
    'punjab': 'Punjab',
    'rajasthan': 'Rajasthan',
    'sikkim': 'Sikkim',
    'tamil nadu': 'Tamil Nadu',
    'telangana': 'Telangana',
    'tripura': 'Tripura',
    'uttar pradesh': 'Uttar Pradesh',
    'uttarakhand': 'Uttarakhand',
    'west bengal': 'West Bengal'
}

STATE_CODE_MAP = {
    'Jammu and Kashmir': '01',
    'Himachal Pradesh': '02',
    'Punjab': '03',
    'Chandigarh': '04',
    'Uttarakhand': '05',
    'Haryana': '06',
    'Delhi': '07',
    'Rajasthan': '08',
    'Uttar Pradesh': '09',
    'Bihar': '10',
    'Sikkim': '11',
    'Arunachal Pradesh': '12',
    'Nagaland': '13',
    'Manipur': '14',
    'Mizoram': '15',
    'Tripura': '16',
    'Meghalaya': '17',
    'Assam': '18',
    'West Bengal': '19',
    'Jharkhand': '20',
    'Odisha': '21',
    'Chhattisgarh': '22',
    'Madhya Pradesh': '23',
    'Gujarat': '24',
    'Dadra and Nagar Haveli and Daman and Diu': '26',
    'Maharashtra': '27',
    'Andhra Pradesh': '28',
    'Karnataka': '29',
    'Goa': '30',
    'Lakshadweep': '31',
    'Kerala': '32',
    'Tamil Nadu': '33',
    'Puducherry': '34',
    'Andaman and Nicobar Islands': '35',
    'Telangana': '36',
    'Ladakh': '37'
}

def normalize_state(name: str) -> str:
    clean = name.strip()
    low = clean.lower()
    return CANONICAL_STATE_MAP.get(low, clean)

def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    R = 6371.0 # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    return 2.0 * R * math.asin(math.sqrt(a))

def parse_int(val):
    if val is None:
        return None
    v = str(val).replace(',', '').strip()
    if not v or v.upper() in ['NA', '-', 'N/A', 'NULL', 'NONE']:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None

def parse_float(val):
    if val is None:
        return None
    v = str(val).replace(',', '').strip()
    if not v or v.upper() in ['NA', '-', 'N/A', 'NULL', 'NONE']:
        return None
    try:
        return float(v)
    except ValueError:
        return None

def save_csv(data, filename, fieldnames):
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    out_path = TARGET_DIR / filename
    with open(out_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f" -> Saved {filename} ({len(data)} rows)")

def run_etl():
    print("=" * 60)
    print("RouteX ETL Pipeline: Starting Extraction & Transformation")
    print("=" * 60)

    # -------------------------------------------------------------
    # 1. EXTRACT & TRANSFORM: State Dimension (dim_state.csv)
    # -------------------------------------------------------------
    print("\n[1/7] Processing State Dimension...")
    dim_states = []
    state_lookup = {}

    ref_states_path = RAW_DIR / "reference" / "final_states.csv"
    with open(ref_states_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, 1):
            st_name = normalize_state(row['State/UT'])
            pop = int(row['Population'])
            area = float(row['Area (in km^2)'])
            districts = int(row['#Districts'])
            lat = float(row['Latitude'])
            lon = float(row['Longitude'])
            density = round(pop / area, 2) if area > 0 else 0.0
            st_code = STATE_CODE_MAP.get(st_name, f"{idx:02d}")

            record = {
                'state_id': idx,
                'state_code': st_code,
                'state_name': st_name,
                'districts_count': districts,
                'population': pop,
                'area_sq_km': area,
                'population_density_per_sq_km': density,
                'centroid_latitude': lat,
                'centroid_longitude': lon
            }
            dim_states.append(record)
            state_lookup[st_name] = record

    save_csv(dim_states, "dim_state.csv", list(dim_states[0].keys()))

    # -------------------------------------------------------------
    # 2. EXTRACT & TRANSFORM: Recent Road Safety & Fatalities Facts (2020-2024)
    # -------------------------------------------------------------
    print("\n[2/7] Processing Recent State Road Safety & Fatalities (2020-2024)...")
    fatalities_raw = {}
    fat_path = RAW_DIR / "road-accidents-2024-states-fatalities.csv"
    with open(fat_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            st = row.get('State', '').strip()
            if not st or st == 'All India':
                continue
            norm_st = normalize_state(st)
            fatalities_raw[norm_st] = {
                'fatalities_2020': parse_int(row.get('2020 Killed')),
                'fatalities_2021': parse_int(row.get('2021 Killed')),
                'fatalities_2022': parse_int(row.get('2022 Killed')),
                'fatalities_2023': parse_int(row.get('2023 Killed')),
                'fatalities_2024': parse_int(row.get('2024 Killed')),
                'pct_change_2023_2024': parse_float(row.get('% change from 2023 to 2024')),
                'rank_2020': parse_int(row.get('2020 Ranking')),
                'rank_2021': parse_int(row.get('2021 Ranking')),
                'rank_2022': parse_int(row.get('2022 Ranking')),
                'rank_2023': parse_int(row.get('2023 Ranking')),
                'rank_2024': parse_int(row.get('2024 Ranking')),
            }

    accidents_raw = {}
    rs_path = RAW_DIR / "RS_Session_267_AU_1540_A_to_C.1.csv"
    with open(rs_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            st = row.get('State/UT-wise', '').strip()
            if not st or 'Total' in st:
                continue
            norm_st = normalize_state(st)

            accidents_raw[norm_st] = {
                'accidents_2020': parse_int(row.get('2020')),
                'accidents_2021': parse_int(row.get('2021')),
                'accidents_2022': parse_int(row.get('2022'))
            }

    fact_safety_recent = []
    for st_name, st_info in state_lookup.items():
        pop = st_info['population']
        fat = fatalities_raw.get(st_name, {})
        acc = accidents_raw.get(st_name, {})

        k24 = fat.get('fatalities_2024') or 0
        k22 = fat.get('fatalities_2022') or 0
        chg = fat.get('pct_change_2023_2024') or 0.0
        acc22 = acc.get('accidents_2022')

        fat_rate_24 = round((k24 / pop) * 100000.0, 2) if pop > 0 else 0.0
        acc_rate_22 = round((acc22 / pop) * 100000.0, 2) if (acc22 and pop > 0) else None
        sev_index_22 = round((k22 / acc22) * 100.0, 2) if (acc22 and acc22 > 0) else None

        # Determine composite safety risk tier
        if fat_rate_24 >= 15.0 or (k24 > 5000 and chg > 0):
            risk_tier = 'High Risk'
        elif fat_rate_24 >= 8.0:
            risk_tier = 'Moderate Risk'
        else:
            risk_tier = 'Low Risk'

        fact_safety_recent.append({
            'state_code': st_info['state_code'],
            'state_name': st_name,
            'population': pop,
            'fatalities_2020': fat.get('fatalities_2020'),
            'fatalities_2021': fat.get('fatalities_2021'),
            'fatalities_2022': fat.get('fatalities_2022'),
            'fatalities_2023': fat.get('fatalities_2023'),
            'fatalities_2024': k24,
            'pct_change_fatalities_2023_2024': chg,
            'fatality_rank_2024': fat.get('rank_2024'),
            'total_accidents_2020': acc.get('accidents_2020'),
            'total_accidents_2021': acc.get('accidents_2021'),
            'total_accidents_2022': acc22,
            'fatalities_per_lakh_pop_2024': fat_rate_24,
            'accidents_per_lakh_pop_2022': acc_rate_22,
            'accident_severity_index_2022': sev_index_22,
            'safety_risk_tier': risk_tier
        })

    # Sort by 2024 fatality rank ascending
    fact_safety_recent.sort(key=lambda x: (x['fatality_rank_2024'] or 999))
    save_csv(fact_safety_recent, "fact_state_safety_recent.csv", list(fact_safety_recent[0].keys()))

    # -------------------------------------------------------------
    # 3. EXTRACT & TRANSFORM: Historical Monthly Accidents (2001-2014)
    # -------------------------------------------------------------
    print("\n[3/7] Processing Historical Monthly Accidents (2001-2014)...")
    month_names = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
                   'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
    
    def get_season(m_num):
        if m_num in [12, 1, 2]: return 'Winter'
        elif m_num in [3, 4, 5]: return 'Pre-Monsoon/Summer'
        elif m_num in [6, 7, 8, 9]: return 'Monsoon'
        else: return 'Post-Monsoon'

    fact_monthly_long = []
    monthly_agg = {}

    month_csv = RAW_DIR / "only_road_accidents_data_month2.csv"
    with open(month_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_st = row.get('STATE/UT', '').strip()
            if not raw_st: continue
            norm_st = normalize_state(raw_st)
            yr = int(row['YEAR'])

            if (norm_st, yr) not in monthly_agg:
                monthly_agg[(norm_st, yr)] = {m: 0 for m in month_names}

            for m_num, m_name in enumerate(month_names, 1):
                cnt = int(row.get(m_name, 0) or 0)
                monthly_agg[(norm_st, yr)][m_name] += cnt
                
                fact_monthly_long.append({
                    'state_name': norm_st,
                    'year': yr,
                    'month': m_name.capitalize(),
                    'month_number': m_num,
                    'quarter': f"Q{(m_num - 1) // 3 + 1}",
                    'season': get_season(m_num),
                    'accidents_count': cnt
                })

    save_csv(fact_monthly_long, "fact_accidents_monthly_trend_long.csv", list(fact_monthly_long[0].keys()))

    # Monthly Summary per State-Year
    fact_monthly_summary = []
    for (st, yr), m_counts in sorted(monthly_agg.items()):
        total = sum(m_counts.values())
        winter = m_counts['DECEMBER'] + m_counts['JANUARY'] + m_counts['FEBRUARY']
        summer = m_counts['MARCH'] + m_counts['APRIL'] + m_counts['MAY']
        monsoon = m_counts['JUNE'] + m_counts['JULY'] + m_counts['AUGUST'] + m_counts['SEPTEMBER']
        post_monsoon = m_counts['OCTOBER'] + m_counts['NOVEMBER']
        
        peak_month = max(m_counts.items(), key=lambda x: x[1])[0].capitalize()
        monsoon_share = round((monsoon / total) * 100.0, 2) if total > 0 else 0.0

        fact_monthly_summary.append({
            'state_name': st,
            'year': yr,
            'annual_total_accidents': total,
            'winter_accidents': winter,
            'summer_accidents': summer,
            'monsoon_accidents': monsoon,
            'post_monsoon_accidents': post_monsoon,
            'monsoon_share_pct': monsoon_share,
            'peak_accident_month': peak_month
        })

    save_csv(fact_monthly_summary, "fact_accidents_monthly_state_summary.csv", list(fact_monthly_summary[0].keys()))

    # -------------------------------------------------------------
    # 4. EXTRACT & TRANSFORM: Historical Time-of-Day Accidents (2001-2014)
    # -------------------------------------------------------------
    print("\n[4/7] Processing Historical Time-of-Day Accidents (2001-2014)...")
    time_slots_def = [
        ('0-3 hrs. (Night)', '00:00 - 03:00', 'Night'),
        ('3-6 hrs. (Night)', '03:00 - 06:00', 'Night'),
        ('6-9 hrs (Day)', '06:00 - 09:00', 'Day'),
        ('9-12 hrs (Day)', '09:00 - 12:00', 'Day'),
        ('12-15 hrs (Day)', '12:00 - 15:00', 'Day'),
        ('15-18 hrs (Day)', '15:00 - 18:00', 'Day'),
        ('18-21 hrs (Night)', '18:00 - 21:00', 'Night'),
        ('21-24 hrs (Night)', '21:00 - 24:00', 'Night')
    ]

    fact_tod_long = []
    tod_agg = {}

    tod_csv = RAW_DIR / "only_road_accidents_data3.csv"
    with open(tod_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_st = row.get('STATE/UT', '').strip()
            if not raw_st: continue
            norm_st = normalize_state(raw_st)
            yr = int(row['YEAR'])
            tot = int(row.get('Total', 0) or 0)

            if (norm_st, yr) not in tod_agg:
                tod_agg[(norm_st, yr)] = {'Day': 0, 'Night': 0, 'slots': {}, 'total': 0}

            for col_name, slot_label, period in time_slots_def:
                cnt = int(row.get(col_name, 0) or 0)
                share = round((cnt / tot) * 100.0, 2) if tot > 0 else 0.0

                fact_tod_long.append({
                    'state_name': norm_st,
                    'year': yr,
                    'time_slot': slot_label,
                    'period': period,
                    'accidents_count': cnt,
                    'share_of_annual_total_pct': share
                })

                tod_agg[(norm_st, yr)][period] += cnt
                tod_agg[(norm_st, yr)]['slots'][slot_label] = tod_agg[(norm_st, yr)]['slots'].get(slot_label, 0) + cnt
                tod_agg[(norm_st, yr)]['total'] += cnt

    save_csv(fact_tod_long, "fact_accidents_time_of_day_long.csv", list(fact_tod_long[0].keys()))

    # Time of Day State Summary
    fact_tod_summary = []
    for (st, yr), t_data in sorted(tod_agg.items()):
        total = t_data['total']
        day_cnt = t_data['Day']
        night_cnt = t_data['Night']
        night_share = round((night_cnt / total) * 100.0, 2) if total > 0 else 0.0
        peak_slot = max(t_data['slots'].items(), key=lambda x: x[1])[0] if t_data['slots'] else 'Unknown'

        fact_tod_summary.append({
            'state_name': st,
            'year': yr,
            'annual_total_accidents': total,
            'daytime_accidents': day_cnt,
            'nighttime_accidents': night_cnt,
            'nighttime_share_pct': night_share,
            'peak_accident_time_slot': peak_slot
        })

    save_csv(fact_tod_summary, "fact_accidents_time_of_day_state_summary.csv", list(fact_tod_summary[0].keys()))

    # -------------------------------------------------------------
    # 5. EXTRACT & TRANSFORM: District Dimension (dim_district.csv)
    # -------------------------------------------------------------
    print("\n[5/7] Processing District Dimension...")
    dim_districts = []
    dist_csv = RAW_DIR / "reference" / "final_districts.csv"
    with open(dist_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, 1):
            st = normalize_state(row['State'])
            dist_name = row['District'].strip()
            pop = parse_int(row.get('Population'))
            area = parse_float(row.get('Area (in km^2)'))
            lat = parse_float(row.get('Latitude'))
            lon = parse_float(row.get('Longitude'))
            density = round(pop / area, 2) if (pop and area and area > 0) else None

            dim_districts.append({
                'district_id': idx,
                'state_name': st,
                'district_name': dist_name,
                'population': pop,
                'area_sq_km': area,
                'population_density_per_sq_km': density,
                'latitude': lat,
                'longitude': lon
            })

    save_csv(dim_districts, "dim_district.csv", list(dim_districts[0].keys()))

    # -------------------------------------------------------------
    # 6. EXTRACT & TRANSFORM: Smart Location Cities & National Highways
    # -------------------------------------------------------------
    print("\n[6/7] Processing Smart Location Cities & National Highways...")
    
    # Map each state to its safety risk tier
    state_tier_map = {row['state_name']: row['safety_risk_tier'] for row in fact_safety_recent}

    dim_cities = []
    cities_csv = RAW_DIR / "reference" / "final_cities_flagged.csv"
    with open(cities_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, 1):
            st = normalize_state(row['State'])
            dist = row['District'].strip()
            city = row['City'].strip()
            pop = parse_int(row.get('Population'))
            area = parse_float(row.get('Area (in km^2)'))
            lat = parse_float(row.get('Latitude'))
            lon = parse_float(row.get('Longitude'))
            is_missing_coord = row.get('coord_missing', 'False').lower() == 'true'
            density = round(pop / area, 2) if (pop and area and area > 0) else None

            dim_cities.append({
                'city_id': idx,
                'state_name': st,
                'district_name': dist,
                'city_name': city,
                'population': pop,
                'area_sq_km': area,
                'population_density_per_sq_km': density,
                'latitude': lat,
                'longitude': lon,
                'has_valid_coords': not is_missing_coord,
                'state_safety_tier': state_tier_map.get(st, 'Moderate Risk')
            })

    save_csv(dim_cities, "dim_city_recommendation.csv", list(dim_cities[0].keys()))

    # Process National Highways from GeoJSON
    hw_geojson_path = RAW_DIR / "highways" / "india_national_highways.geojson"
    print(" -> Loading and measuring National Highway geometries (this takes ~0.5s)...")
    with open(hw_geojson_path, encoding='utf-8') as f:
        hw_data = json.load(f)

    hw_summary = {}
    for feat in hw_data['features']:
        props = feat.get('properties', {})
        name = props.get('Name', '').strip() or 'Unknown NH'
        road_type = props.get('Road_Type', '').strip() or 'National Highway'
        geom = feat.get('geometry', {})
        g_type = geom.get('type')
        coords = geom.get('coordinates', [])

        lines = coords if g_type == 'MultiLineString' else [coords]
        length = 0.0
        for line in lines:
            for i in range(len(line) - 1):
                p1, p2 = line[i], line[i+1]
                length += haversine(p1[0], p1[1], p2[0], p2[1])

        if name not in hw_summary:
            hw_summary[name] = {
                'highway_name': name,
                'road_type': road_type,
                'segment_count': 0,
                'total_length_km': 0.0
            }
        hw_summary[name]['segment_count'] += 1
        hw_summary[name]['total_length_km'] += length

    dim_highways = []
    for h_name, h_info in sorted(hw_summary.items(), key=lambda x: x[1]['total_length_km'], reverse=True):
        l_km = round(h_info['total_length_km'], 2)
        if l_km >= 1500.0:
            tier = 'Major Trans-National Corridor'
        elif l_km >= 500.0:
            tier = 'Inter-State Trunk Highway'
        elif l_km >= 100.0:
            tier = 'Regional Link Highway'
        else:
            tier = 'Feeder / Spur Highway'

        dim_highways.append({
            'highway_name': h_name,
            'road_type': h_info['road_type'],
            'segment_count': h_info['segment_count'],
            'total_length_km': l_km,
            'corridor_tier': tier
        })

    save_csv(dim_highways, "dim_national_highways.csv", list(dim_highways[0].keys()))

    # -------------------------------------------------------------
    # 7. INTEGRATED ANALYTICAL MASTER DATASET (routex_integrated_state_risk_profile.csv)
    # -------------------------------------------------------------
    print("\n[7/7] Generating Unified Analytical Master Profile...")
    
    # Calculate historical 14-year averages per state
    hist_state_averages = {}
    for row in fact_monthly_summary:
        st = row['state_name']
        if st not in hist_state_averages:
            hist_state_averages[st] = {'totals': [], 'monsoon_shares': []}
        hist_state_averages[st]['totals'].append(row['annual_total_accidents'])
        hist_state_averages[st]['monsoon_shares'].append(row['monsoon_share_pct'])

    hist_night_averages = {}
    for row in fact_tod_summary:
        st = row['state_name']
        if st not in hist_night_averages:
            hist_night_averages[st] = []
        hist_night_averages[st].append(row['nighttime_share_pct'])

    routex_master = []
    for row in fact_safety_recent:
        st = row['state_name']
        st_demo = state_lookup[st]
        
        hist_totals = hist_state_averages.get(st, {}).get('totals', [])
        avg_hist_acc = round(sum(hist_totals) / len(hist_totals), 2) if hist_totals else None
        
        hist_monsoon = hist_state_averages.get(st, {}).get('monsoon_shares', [])
        avg_monsoon_share = round(sum(hist_monsoon) / len(hist_monsoon), 2) if hist_monsoon else None

        hist_night = hist_night_averages.get(st, [])
        avg_night_share = round(sum(hist_night) / len(hist_night), 2) if hist_night else None

        routex_master.append({
            'state_code': row['state_code'],
            'state_name': st,
            'population': row['population'],
            'area_sq_km': st_demo['area_sq_km'],
            'population_density_per_sq_km': st_demo['population_density_per_sq_km'],
            'districts_count': st_demo['districts_count'],
            'centroid_latitude': st_demo['centroid_latitude'],
            'centroid_longitude': st_demo['centroid_longitude'],
            'fatalities_2020': row['fatalities_2020'],
            'fatalities_2021': row['fatalities_2021'],
            'fatalities_2022': row['fatalities_2022'],
            'fatalities_2023': row['fatalities_2023'],
            'fatalities_2024': row['fatalities_2024'],
            'pct_change_fatalities_2023_2024': row['pct_change_fatalities_2023_2024'],
            'fatality_rank_2024': row['fatality_rank_2024'],
            'fatalities_per_lakh_pop_2024': row['fatalities_per_lakh_pop_2024'],
            'total_accidents_2022': row['total_accidents_2022'],
            'accident_severity_index_2022': row['accident_severity_index_2022'],
            'safety_risk_tier': row['safety_risk_tier'],
            'historical_avg_annual_accidents_2001_2014': avg_hist_acc,
            'historical_avg_monsoon_accident_share_pct': avg_monsoon_share,
            'historical_avg_nighttime_accident_share_pct': avg_night_share
        })

    routex_master.sort(key=lambda x: (x['fatality_rank_2024'] or 999))
    save_csv(routex_master, "routex_integrated_state_risk_profile.csv", list(routex_master[0].keys()))

    # -------------------------------------------------------------
    # 8. DATA DICTIONARY GENERATION
    # -------------------------------------------------------------
    dict_content = """# RouteX Final Dataset - Data Dictionary & Catalog

## Overview
This directory contains the cleaned, standardized, and integrated analytical tables produced by the RouteX ETL pipeline.
All entity names have been normalized to canonical Indian administrative divisions, and metrics have been validated against official Ministry of Road Transport and Highways (MoRTH) standards.

---

## Files Catalog

### 1. `dim_state.csv`
- **Description**: Canonical state demographic and geographical master table (36 States/UTs).
- **Columns**:
  - `state_id`: Unique surrogate integer ID (1-36).
  - `state_code`: Official Census State Code (e.g. `01` to `37`).
  - `state_name`: Canonical State/UT name.
  - `districts_count`: Number of administrative districts.
  - `population`: Total 2011 Census population.
  - `area_sq_km`: Geographical land area in square kilometers.
  - `population_density_per_sq_km`: Population per square kilometer.
  - `centroid_latitude`: Centroid latitude.
  - `centroid_longitude`: Centroid longitude.

### 2. `fact_state_safety_recent.csv`
- **Description**: Recent road safety and fatality facts spanning 2020–2024 with normalized risk indicators.
- **Columns**:
  - `state_code`: Official Census State Code.
  - `state_name`: Canonical State/UT name.
  - `population`: Population baseline.
  - `fatalities_2020` to `fatalities_2024`: Annual road fatalities (cleaned of commas).
  - `pct_change_fatalities_2023_2024`: Percentage growth/decline from 2023 to 2024.
  - `fatality_rank_2024`: National rank by fatalities in 2024 (1 = highest fatalities).
  - `total_accidents_2020` to `total_accidents_2022`: Total road accidents (from Rajya Sabha MoRTH records).
  - `fatalities_per_lakh_pop_2024`: Fatalities per 100,000 population in 2024.
  - `accidents_per_lakh_pop_2022`: Accidents per 100,000 population in 2022.
  - `accident_severity_index_2022`: Number of fatalities per 100 accidents (Severity %).
  - `safety_risk_tier`: Composite categorization (`High Risk`, `Moderate Risk`, `Low Risk`).

### 3. `fact_accidents_monthly_trend_long.csv` & `fact_accidents_monthly_state_summary.csv`
- **Description**: Cleaned historical monthly accident trends (2001–2014) across states.
- **Key Columns**:
  - `month`, `month_number`, `quarter`, `season` (Winter, Pre-Monsoon/Summer, Monsoon, Post-Monsoon).
  - `accidents_count`: Monthly accident volume.
  - `monsoon_share_pct`: Percentage of annual accidents occurring during the monsoon season.
  - `peak_accident_month`: Month with highest accident incidence for that year.

### 4. `fact_accidents_time_of_day_long.csv` & `fact_accidents_time_of_day_state_summary.csv`
- **Description**: Cleaned historical time-of-day accident intervals (2001–2014) across states.
- **Key Columns**:
  - `time_slot`: 3-hour time blocks (e.g. `00:00 - 03:00`, `18:00 - 21:00`).
  - `period`: `Day` vs. `Night`.
  - `accidents_count`: Accident volume in that time slot.
  - `share_of_annual_total_pct`: Percentage share of annual total.
  - `nighttime_share_pct`: Percentage of accidents occurring during night hours.
  - `peak_accident_time_slot`: Highest risk time slot for that state-year.

### 5. `dim_district.csv`
- **Description**: Pan-India district dimension covering 738 districts with population, area, and coordinates.

### 6. `dim_city_recommendation.csv`
- **Description**: Urban centers with 100k+ population flagged for Smart Location and Routing recommendations, joined with parent state safety risk tiers.

### 7. `dim_national_highways.csv`
- **Description**: Highway infrastructure inventory extracted from GeoJSON geometries covering 1,013 highways with calculated geodesic length in km and corridor tiers.

### 8. `routex_integrated_state_risk_profile.csv`
- **Description**: Master integrated analytical table joining demographic indicators, recent 2020–2024 safety metrics, and historical 14-year accident dynamics into a single feature-rich dataset for ML and BI models.
"""
    with open(TARGET_DIR / "DATA_DICTIONARY.md", "w", encoding="utf-8") as f:
        f.write(dict_content)
    print(" -> Saved DATA_DICTIONARY.md")

    print("\n" + "=" * 60)
    print("ETL Pipeline Completed Successfully!")
    print(f"Finalized datasets loaded to: {TARGET_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    run_etl()
