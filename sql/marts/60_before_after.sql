-- One row per bus route (62): before (feed 2026-09-10) against after (feed 2026-09-29).
--
-- tier_before / tier_after: the route_compliance tier on Wed 2026-09-30 and Wed 2026-10-14. A route missing from a
--   feed's routes.txt counts as "no service on date" on that side.
-- change, bus routes: order 15-min > 30-min > below standard > no service on date.
--   up / down: the after tier is higher / lower than the before tier, both sides with service.
--   same: equal tiers, or no service on either date.
--   new: no service on the before date, service on the after date. gone: the reverse.
-- change, express routes: no headway tier, so the order is express pass > express fail > no service on date, with
--   new, gone and same as for bus routes.
-- Median columns: the route's median for the period, taken as the longest median over its scored directions;
--   NULL when the route has no service on the date or any scored direction has fewer than 2 departures in the period.
-- Weekend columns (sat_*, sun_*) are report only: Saturday and Sunday pairs, no tier and no up or down.
create or replace table before_after as
with routes as (
    select distinct route_short_name, category from bus_routes
),
route_period as (
    select
        feed_version, date, route_short_name, period,
        case when bool_or(headway_median_s is null) then null else max(headway_median_s) end as route_median_s
    from route_period_headway
    group by feed_version, date, route_short_name, period
),
route_wide as (
    select
        feed_version, date, route_short_name,
        max(route_median_s) filter (where period = 'am_peak') as am_peak_median_s,
        max(route_median_s) filter (where period = 'midday') as midday_median_s,
        max(route_median_s) filter (where period = 'pm_peak') as pm_peak_median_s,
        max(route_median_s) filter (where period = 'evening') as evening_median_s,
        max(route_median_s) filter (where period = 'weekend_day') as weekend_day_median_s
    from route_period
    group by feed_version, date, route_short_name
),
side_rows as (
    select c.*, cd.side, w.am_peak_median_s, w.midday_median_s, w.pm_peak_median_s, w.evening_median_s,
        w.weekend_day_median_s,
        case
            when c.no_service_on_date then 0
            when c.category = 'express' then case when c.express_pass then 2 else 1 end
            else case c.tier when '15-min' then 3 when '30-min' then 2 else 1 end
        end as tier_rank
    from route_compliance c
    join comparison_dates cd on cd.feed_version = c.feed_version and cd.date = c.date
    left join route_wide w
        on w.feed_version = c.feed_version and w.date = c.date and w.route_short_name = c.route_short_name
),
joined as (
    select
        r.route_short_name, r.category,
        bw.tier as tier_before, aw.tier as tier_after,
        coalesce(not bw.no_service_on_date, false) as served_before,
        coalesce(not aw.no_service_on_date, false) as served_after,
        coalesce(bw.tier_rank, 0) as rank_before,
        coalesce(aw.tier_rank, 0) as rank_after,
        bw.express_pass as express_pass_before, aw.express_pass as express_pass_after,
        bw.span_start as span_start_before, bw.span_end as span_end_before, bw.span_pass as span_pass_before,
        aw.span_start as span_start_after, aw.span_end as span_end_after, aw.span_pass as span_pass_after,
        bw.am_peak_median_s as am_peak_median_before_s, aw.am_peak_median_s as am_peak_median_after_s,
        bw.midday_median_s as midday_median_before_s, aw.midday_median_s as midday_median_after_s,
        bw.pm_peak_median_s as pm_peak_median_before_s, aw.pm_peak_median_s as pm_peak_median_after_s,
        bw.evening_median_s as evening_median_before_s, aw.evening_median_s as evening_median_after_s,
        bsat.tier as sat_status_before, asat.tier as sat_status_after,
        bsat.weekend_day_median_s as sat_median_before_s, asat.weekend_day_median_s as sat_median_after_s,
        bsat.span_pass as sat_span_pass_before, asat.span_pass as sat_span_pass_after,
        bsun.tier as sun_status_before, asun.tier as sun_status_after,
        bsun.weekend_day_median_s as sun_median_before_s, asun.weekend_day_median_s as sun_median_after_s,
        bsun.span_pass as sun_span_pass_before, asun.span_pass as sun_span_pass_after
    from routes r
    left join side_rows bw on bw.route_short_name = r.route_short_name and bw.day_type = 'weekday' and bw.side = 'before'
    left join side_rows aw on aw.route_short_name = r.route_short_name and aw.day_type = 'weekday' and aw.side = 'after'
    left join side_rows bsat on bsat.route_short_name = r.route_short_name and bsat.day_type = 'saturday' and bsat.side = 'before'
    left join side_rows asat on asat.route_short_name = r.route_short_name and asat.day_type = 'saturday' and asat.side = 'after'
    left join side_rows bsun on bsun.route_short_name = r.route_short_name and bsun.day_type = 'sunday' and bsun.side = 'before'
    left join side_rows asun on asun.route_short_name = r.route_short_name and asun.day_type = 'sunday' and asun.side = 'after'
)
select
    route_short_name,
    category,
    coalesce(tier_before, 'no service on date') as tier_before,
    coalesce(tier_after, 'no service on date') as tier_after,
    case
        when not served_before and not served_after then 'same'
        when not served_before then 'new'
        when not served_after then 'gone'
        when rank_after > rank_before then 'up'
        when rank_after < rank_before then 'down'
        else 'same'
    end as change,
    express_pass_before, express_pass_after,
    span_start_before, span_end_before, span_pass_before,
    span_start_after, span_end_after, span_pass_after,
    am_peak_median_before_s, am_peak_median_after_s,
    midday_median_before_s, midday_median_after_s,
    pm_peak_median_before_s, pm_peak_median_after_s,
    evening_median_before_s, evening_median_after_s,
    coalesce(sat_status_before, 'no service on date') as sat_status_before,
    coalesce(sat_status_after, 'no service on date') as sat_status_after,
    sat_median_before_s, sat_median_after_s, sat_span_pass_before, sat_span_pass_after,
    coalesce(sun_status_before, 'no service on date') as sun_status_before,
    coalesce(sun_status_after, 'no service on date') as sun_status_after,
    sun_median_before_s, sun_median_after_s, sun_span_pass_before, sun_span_pass_after
from joined;
