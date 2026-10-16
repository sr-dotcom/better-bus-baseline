-- First-stop departures that fall in a period, with the gap to the previous departure of the same route and
-- direction in that period. Two trips at the same time give a gap of 0. The first departure of a period has no gap.
create or replace table period_departures as
select
    f.feed_version,
    f.date,
    f.day_type,
    f.route_short_name,
    f.direction_id,
    p.period,
    f.trip_id,
    f.departure_s,
    f.departure_s - lag(f.departure_s) over (
        partition by f.feed_version, f.date, f.route_short_name, f.direction_id, p.period
        order by f.departure_s, f.trip_id
    ) as gap_s
from first_stop_departures f
join periods p on p.day_type = f.day_type and f.departure_s >= p.start_s and f.departure_s < p.end_s;
