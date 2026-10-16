-- Express routes only, weekday dates only (MTC-06 2.4: weekday only commuter routes). One row per feed_version, date,
-- express route with service on the date, and peak (am_peak, pm_peak).
-- MTC-06 3.7: "a minimum of three trips in each peak direction", read as the peak-flow direction: the direction with
-- more trips in that peak. A tie gives the shared count (peak_flow_direction is NULL then); the other direction is
-- ignored. passes: peak_flow_count >= 3.
create or replace table express_peak_trips as
with slots as (
    select distinct a.feed_version, a.date, a.route_short_name, p.period
    from active_trips a
    join bus_routes r on r.feed_version = a.feed_version and r.route_short_name = a.route_short_name
    join periods p on p.day_type = a.day_type
    where r.is_express and p.period in ('am_peak', 'pm_peak')
),
counts as (
    select
        s.feed_version, s.date, s.route_short_name, s.period,
        count(d.trip_id) filter (where d.direction_id = 0) as trips_direction_0,
        count(d.trip_id) filter (where d.direction_id = 1) as trips_direction_1
    from slots s
    left join period_departures d
        on d.feed_version = s.feed_version and d.date = s.date and d.route_short_name = s.route_short_name
        and d.period = s.period
    group by s.feed_version, s.date, s.route_short_name, s.period
)
select
    feed_version, date, route_short_name, period,
    trips_direction_0,
    trips_direction_1,
    greatest(trips_direction_0, trips_direction_1) as peak_flow_count,
    case
        when trips_direction_0 > trips_direction_1 then 0
        when trips_direction_1 > trips_direction_0 then 1
    end as peak_flow_direction,
    greatest(trips_direction_0, trips_direction_1) >= 3 as passes
from counts;
