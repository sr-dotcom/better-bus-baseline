-- One row per active trip: the arrival at its last stop, the stop_times row with the highest stop_sequence.
-- Times past 24:00:00 belong to the same service day (25:30:00 is 01:30 the next morning).
create or replace table last_stop_arrivals as
select
    a.feed_version,
    a.date,
    a.day_type,
    a.trip_id,
    a.route_short_name,
    a.direction_id,
    arg_max(s.stop_id, s.stop_sequence) as stop_id,
    max(s.stop_sequence) as stop_sequence,
    arg_max(s.arrival_s, s.stop_sequence) as arrival_s
from active_trips a
join stg_stop_times s on s.feed_version = a.feed_version and s.trip_id = a.trip_id
group by a.feed_version, a.date, a.day_type, a.trip_id, a.route_short_name, a.direction_id;
