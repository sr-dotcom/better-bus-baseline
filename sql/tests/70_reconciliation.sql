-- test: marts reconcile with the raw tables and with each other
-- Offending rows: the check that failed, with the two numbers that should be equal.
with raw_active as (
    -- Active bus trips counted straight from the raw text tables, independent of staging and the intermediate models.
    select cd.feed_version, cd.date, count(distinct t.trip_id) as n
    from comparison_dates cd
    join raw_calendar_dates c
        on c.feed_version = cd.feed_version and c.date = strftime(cd.date, '%Y%m%d') and c.exception_type = '1'
    join raw_trips t on t.feed_version = cd.feed_version and t.service_id = c.service_id
    join raw_routes r on r.feed_version = t.feed_version and r.route_id = t.route_id and r.route_type = '3'
    group by cd.feed_version, cd.date
),
model_active as (
    select feed_version, date, count(*) as n from active_trips group by feed_version, date
)
select 'active trips: raw count vs active_trips' as what, r.feed_version, r.date, r.n as left_n, m.n as right_n
from raw_active r
left join model_active m on m.feed_version = r.feed_version and m.date = r.date
where m.n is distinct from r.n
union all
select 'trips: active_trips vs first_stop_departures', a.feed_version, a.date, a.n, f.n
from model_active a
left join (select feed_version, date, count(*) as n from first_stop_departures group by feed_version, date) f
    on f.feed_version = a.feed_version and f.date = a.date
where f.n is distinct from a.n
union all
select 'trips: active_trips vs last_stop_arrivals', a.feed_version, a.date, a.n, l.n
from model_active a
left join (select feed_version, date, count(*) as n from last_stop_arrivals group by feed_version, date) l
    on l.feed_version = a.feed_version and l.date = a.date
where l.n is distinct from a.n
union all
select 'trips: active_trips vs route_compliance n_trips', a.feed_version, a.date, a.n, c.n
from model_active a
left join (select feed_version, date, sum(n_trips) as n from route_compliance group by feed_version, date) c
    on c.feed_version = a.feed_version and c.date = a.date
where c.n is distinct from a.n
union all
select 'trips: active_trips vs route_span n_trips', a.feed_version, a.date, a.n, s.n
from model_active a
left join (select feed_version, date, sum(n_trips) as n from route_span group by feed_version, date) s
    on s.feed_version = a.feed_version and s.date = a.date
where s.n is distinct from a.n
union all
-- Every first-stop departure inside a period is counted once in route_period_headway.
select 'period departures: period_departures vs route_period_headway n_departures', d.feed_version, d.date, d.n, h.n
from (select feed_version, date, count(*) as n from period_departures group by feed_version, date) d
left join (select feed_version, date, sum(n_departures) as n from route_period_headway group by feed_version, date) h
    on h.feed_version = d.feed_version and h.date = d.date
where h.n is distinct from d.n
union all
-- The periods table matches the periods the decisions name (sheet decision 1).
select 'periods table', 'n/a', null, count(*), 6
from periods
having count(*) <> 6
union all
-- Express routes have no span verdict and no headway verdict; local routes always have a span verdict.
select 'express route with a span verdict or headway verdict', feed_version, date, count(*), 0
from route_span s
where (category = 'express' and span_pass is not null) or (category = 'bus' and span_pass is null)
group by feed_version, date
union all
select 'express route with headway verdict', feed_version, date, count(*), 0
from route_period_headway
where category = 'express' and (passes_15 is not null or passes_30 is not null or reason_15 is not null)
group by feed_version, date
union all
-- A failed scored period always has a reason; a passed one never has.
select 'failed period without a reason, or passed period with one', feed_version, date, count(*), 0
from route_period_headway
where (passes_15 = false and reason_15 is null) or (passes_15 and reason_15 is not null)
   or (passes_30 = false and reason_30 is null) or (passes_30 and reason_30 is not null)
group by feed_version, date
union all
-- Before and after: one row per route, with the change values from the documented set.
select 'before_after change value', 'n/a', null, count(*), 0
from before_after
where change not in ('up', 'down', 'same', 'new', 'gone')
having count(*) > 0;
