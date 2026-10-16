create or replace view stg_stops as
select * exclude (loaded_at_utc) replace (
    cast(stop_lat as double) as stop_lat,
    cast(stop_lon as double) as stop_lon,
    try_cast(nullif(location_type, '') as integer) as location_type
)
from raw_stops;
