-- Times as seconds since service-day start (UTC does not apply: GTFS times are the agency's local clock).
-- stop_sequence is an integer: as text "10" sorts before "9", which would pick the wrong first stop.
create or replace view stg_stop_times as
select
    feed_version,
    trip_id,
    cast(stop_sequence as integer) as stop_sequence,
    stop_id,
    gtfs_seconds(arrival_time) as arrival_s,
    gtfs_seconds(departure_time) as departure_s,
    arrival_time as arrival_time_text,
    departure_time as departure_time_text,
    try_cast(nullif(pickup_type, '') as integer) as pickup_type,
    try_cast(nullif(drop_off_type, '') as integer) as drop_off_type,
    try_cast(nullif(timepoint, '') as integer) as timepoint
from raw_stop_times;
