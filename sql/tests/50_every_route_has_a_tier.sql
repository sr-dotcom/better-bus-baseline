-- test: every bus route in each feed's routes.txt appears on every date of its feed with a tier or "no service on date"
-- Offending rows: a route and date with no route_compliance row, a tier outside the allowed set, or a weekday
-- tier that disagrees with whether the route has trips.
with expected as (
    select r.feed_version, r.route_short_name, cd.date, cd.day_type
    from raw_routes r
    join comparison_dates cd on cd.feed_version = r.feed_version
    where r.route_type = '3'
)
select e.feed_version, e.date, e.route_short_name, c.tier, 'missing or tier not allowed' as problem
from expected e
left join route_compliance c
    on c.feed_version = e.feed_version and c.date = e.date and c.route_short_name = e.route_short_name
where c.tier is null
   or c.tier not in ('15-min', '30-min', 'below standard', 'no service on date', 'report only', 'not scored (express)')
union all
select feed_version, date, route_short_name, tier, 'no trips but a tier'
from route_compliance
where no_service_on_date and tier <> 'no service on date'
union all
select feed_version, date, route_short_name, tier, 'trips but no service tier'
from route_compliance
where not no_service_on_date and tier = 'no service on date'
union all
select feed_version, date, route_short_name, tier, 'weekday local route without a 15-min, 30-min or below standard tier'
from route_compliance
where day_type = 'weekday' and category = 'bus' and not no_service_on_date
  and tier not in ('15-min', '30-min', 'below standard')
union all
select feed_version, date, route_short_name, tier, 'weekend route not marked report only'
from route_compliance
where day_type <> 'weekday' and not no_service_on_date and tier <> 'report only';
