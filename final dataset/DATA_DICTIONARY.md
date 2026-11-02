# RouteX Final Dataset - Data Dictionary & Catalog

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
