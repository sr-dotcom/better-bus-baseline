-- test: the key of every mart (and of the trip-level intermediate tables) is unique
-- Offending rows: the table and how many key values repeat.
select 'route_period_headway' as tbl, count(*) as repeated_keys
from (select 1 from route_period_headway group by feed_version, date, route_short_name, direction_id, period having count(*) > 1)
having count(*) > 0
union all
select 'route_span', count(*)
from (select 1 from route_span group by feed_version, date, route_short_name having count(*) > 1)
having count(*) > 0
union all
select 'express_peak_trips', count(*)
from (select 1 from express_peak_trips group by feed_version, date, route_short_name, period having count(*) > 1)
having count(*) > 0
union all
select 'route_compliance', count(*)
from (select 1 from route_compliance group by feed_version, date, route_short_name having count(*) > 1)
having count(*) > 0
union all
select 'before_after_headway', count(*)
from (select 1 from before_after_headway group by day_type, route_short_name, direction_id, period having count(*) > 1)
having count(*) > 0
union all
select 'before_after', count(*)
from (select 1 from before_after group by route_short_name having count(*) > 1)
having count(*) > 0
union all
select 'active_trips', count(*)
from (select 1 from active_trips group by feed_version, date, trip_id having count(*) > 1)
having count(*) > 0
union all
select 'first_stop_departures', count(*)
from (select 1 from first_stop_departures group by feed_version, date, trip_id having count(*) > 1)
having count(*) > 0
union all
select 'last_stop_arrivals', count(*)
from (select 1 from last_stop_arrivals group by feed_version, date, trip_id having count(*) > 1)
having count(*) > 0;
