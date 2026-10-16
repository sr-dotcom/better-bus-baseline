-- test: route_compliance has one row per bus route in each feed's routes.txt on each of the six dates, 62 on Wed 2026-10-14
-- The expected count comes from the raw routes table (route_type 3), not from the staging view. Rail (501, 510) is out.
with expected as (
    select cd.feed_version, cd.date, count(*) as expected_routes
    from comparison_dates cd
    join raw_routes r on r.feed_version = cd.feed_version and r.route_type = '3'
    group by cd.feed_version, cd.date
),
actual as (
    select feed_version, date, count(*) as actual_rows, count(distinct route_short_name) as actual_routes
    from route_compliance
    group by feed_version, date
)
select e.feed_version, e.date, e.expected_routes, a.actual_rows, a.actual_routes
from expected e
left join actual a on a.feed_version = e.feed_version and a.date = e.date
where a.actual_rows is distinct from e.expected_routes or a.actual_routes is distinct from e.expected_routes
union all
-- The brief's figure: 64 routes in routes.txt minus the 2 rail routes.
select feed_version, date, 62, count(*), count(distinct route_short_name)
from route_compliance
where date = date '2026-10-14'
group by feed_version, date
having count(*) <> 62
union all
select feed_version, date, 0, count(*), count(distinct route_short_name)
from route_compliance
where route_short_name in ('501', '510')
group by feed_version, date
union all
-- 14 express routes with service on each Wednesday, two peaks each.
select feed_version, date, 28, count(*), count(distinct route_short_name)
from express_peak_trips
group by feed_version, date
having count(*) <> 28
union all
-- Express peak trips exist for weekday dates only.
select e.feed_version, e.date, 0, count(*), count(distinct e.route_short_name)
from express_peak_trips e
join comparison_dates cd on cd.feed_version = e.feed_version and cd.date = e.date
where cd.day_type <> 'weekday'
group by e.feed_version, e.date;
