# Research & Literature Review — RouteX Traffic & Road Safety Analytics

## 1. Overview & Context
RouteX is an intelligent road safety and traffic analytics platform designed to ingest raw accident datasets, highway networks, and demographic statistics, transform them via an Extract, Transform, Load (ETL) pipeline into a multidimensional On-Line Analytical Processing (OLAP) star schema, and serve insights via secure web dashboards.

## 2. Existing Systems & Literature Review
- **Integrated Road Accident Database (iRAD)**: A centralized accident database system initiated by the Ministry of Road Transport and Highways (MoRTH), India, capturing crash data, vehicle details, and road engineering parameters.
- **Global Road Safety Observatory (GRSO)**: International benchmark platform providing cross-country comparison of traffic fatalities, injury severity indices, and diurnal risk distribution.
- **FHWA Highway Safety Information System (HSIS)**: Multistate database used by transportation engineers for safety research, road geometry correlation, and predictive accident modeling.

## 3. Architecture & Methodology
- **Data Layer**: SQLite databases (`routex_olap.db`, `users.db`) storing star schema dimension tables (`dim_state`, `dim_district`, `dim_national_highways`) and fact tables (`fact_accidents_monthly_trend_long`, `fact_accidents_time_of_day_long`).
- **OLAP Engine**: Python-based multidimensional aggregation engine supporting slicing, dicing, roll-up, drill-down, and diurnal risk profiling.
- **Security & Access Control**: Secure HTTP server enforcing authentication cookies (`routex_user`), password hashing via SHA-256, and restricted view access before user login/signup.

## 4. References
1. Ministry of Road Transport and Highways (MoRTH). Annual Report on Road Accidents in India.
2. World Health Organization (WHO). Global Status Report on Road Safety.
3. Kimball, R., & Ross, M. (2013). The Data Warehouse Toolkit: The Definitive Guide to Dimensional Modeling (3rd ed.). Wiley.
