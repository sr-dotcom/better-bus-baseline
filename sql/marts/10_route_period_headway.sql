-- Headway per route, direction and period on each comparison date. One row per feed_version, date, route, direction,
-- period, for every direction that has at least one active trip on the date. Times are seconds (UTC does not apply:
-- GTFS times are the agency's local clock, not timestamps).
--
-- headway_median_s: median of the gaps between consecutive first-stop departures in the period. quantile_cont gives
--   the mean of the two middle gaps for an even number of gaps. NULL when fewer than 2 departures (no headway).
-- headway_max_s: largest gap, reported beside the median and not scored.
-- covers_15 / covers_30: whether the period is scored against that standard (from periods). Local bus routes only;
--   express routes have no headway test.
-- passes_15 / passes_30: median <= limit (MTC-06 3.7: 15:00 passes 15, 30:00 passes 30). NULL when the period is not
--   scored for that standard (evening, weekend, midday for 15) or the route is express. A scored period with fewer
--   than 2 departures is false, not NULL.
-- reason_15 / reason_30: NULL when the period passes or is not scored; otherwise why it failed.
create or replace table route_period_headway as
with slots as (
    select distinct a.feed_version, a.date, a.day_type, a.route_short_name, a.direction_id
    from active_trips a
),
agg as (
    select
        feed_version, date, route_short_name, direction_id, period,
        count(*) as n_departures,
        quantile_cont(gap_s, 0.5) as headway_median_s,
        max(gap_s) as headway_max_s
    from period_departures
    group by feed_version, date, route_short_name, direction_id, period
),
scored as (
    select
        s.feed_version, s.date, s.day_type, s.route_short_name, r.category, s.direction_id,
        p.period, p.sort_order,
        coalesce(g.n_departures, 0) as n_departures,
        g.headway_median_s,
        g.headway_max_s,
        r.category = 'bus' and p.covers_15 as covers_15,
        r.category = 'bus' and p.covers_30 as covers_30
    from slots s
    join bus_routes r on r.feed_version = s.feed_version and r.route_short_name = s.route_short_name
    join periods p on p.day_type = s.day_type
    left join agg g
        on g.feed_version = s.feed_version and g.date = s.date and g.route_short_name = s.route_short_name
        and g.direction_id = s.direction_id and g.period = p.period
)
select
    feed_version, date, day_type, route_short_name, category, direction_id, period,
    n_departures,
    headway_median_s,
    headway_max_s,
    covers_15,
    covers_30,
    case when covers_15 then coalesce(headway_median_s <= 900, false) end as passes_15,
    case when covers_30 then coalesce(headway_median_s <= 1800, false) end as passes_30,
    case
        when not covers_15 then null
        when n_departures < 2 then 'fewer than 2 departures in period'
        when headway_median_s > 900 then 'headway above standard'
    end as reason_15,
    case
        when not covers_30 then null
        when n_departures < 2 then 'fewer than 2 departures in period'
        when headway_median_s > 1800 then 'headway above standard'
    end as reason_30
from scored;
