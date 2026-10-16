-- After minus before for the same route, direction, period and day type (docs/metrics.md, before_after_change).
-- One row per day_type, route, direction and period that has headway rows on either side. The before side is the
-- earlier date (feed 2026-09-10), the after side the later date (feed 2026-09-29).
-- *_change_s: after minus before, in seconds; NULL when either side has no headway (fewer than 2 departures) or the
-- direction runs on only one side.
create or replace table before_after_headway as
with side as (
    select h.*, cd.side
    from route_period_headway h
    join comparison_dates cd on cd.feed_version = h.feed_version and cd.date = h.date
)
select
    coalesce(b.day_type, a.day_type) as day_type,
    coalesce(b.route_short_name, a.route_short_name) as route_short_name,
    coalesce(b.category, a.category) as category,
    coalesce(b.direction_id, a.direction_id) as direction_id,
    coalesce(b.period, a.period) as period,
    (select min(date) from comparison_dates where side = 'before' and day_type = coalesce(b.day_type, a.day_type))
        as before_date,
    (select min(date) from comparison_dates where side = 'after' and day_type = coalesce(b.day_type, a.day_type))
        as after_date,
    b.n_departures as n_before,
    a.n_departures as n_after,
    b.headway_median_s as median_before_s,
    a.headway_median_s as median_after_s,
    a.headway_median_s - b.headway_median_s as median_change_s,
    b.headway_max_s as max_before_s,
    a.headway_max_s as max_after_s,
    a.headway_max_s - b.headway_max_s as max_change_s
from (select * from side where side = 'before') b
full join (select * from side where side = 'after') a
    on a.day_type = b.day_type and a.route_short_name = b.route_short_name
    and a.direction_id = b.direction_id and a.period = b.period;
