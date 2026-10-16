-- One row per active trip: the departure from its first stop, the stop_times row with the lowest stop_sequence
-- (an integer from staging). The time is seconds since service-day start.
create or replace table first_stop_departures as
select
    a.feed_version,
    a.date,
    a.day_type,
    a.trip_id,
    a.route_short_name,
    a.direction_id,
    arg_min(s.stop_id, s.stop_sequence) as stop_id,
    min(s.stop_sequence) as stop_sequence,
    arg_min(s.departure_s, s.stop_sequence) as departure_s
from active_trips a
join stg_stop_times s on s.feed_version = a.feed_version and s.trip_id = a.trip_id
group by a.feed_version, a.date, a.day_type, a.trip_id, a.route_short_name, a.direction_id;
