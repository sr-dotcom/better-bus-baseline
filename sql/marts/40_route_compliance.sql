-- One row per feed_version, date and bus route in that feed's routes.txt (62 per date), whether or not it runs.
--
-- category: express (route_short_name ends in x) or bus.
-- tier (docs/metrics.md decision 4):
--   weekday bus route: "15-min" if tier_15_pass, else "30-min" if tier_30_pass, else "below standard"
--   "no service on date": the route has no active trip on the date (no_service_on_date is true)
--   "report only": a Saturday or Sunday date with service; MTC-06 sets no weekend standard, so no verdict is shown
--   "not scored (express)": express routes have no headway tier; see express_pass
-- tier_15_pass / tier_30_pass: every scored direction passes in every covered period (NULL when not scored).
-- weakest_*: the direction and period with the longest median among the periods the 30-minute standard covers
--   (weekday AM peak, midday, PM peak) or the weekend daytime period. A direction with no headway (fewer than 2
--   departures) is weaker than any median; its weakest_median_s is NULL. NULL for express routes.
-- fail_reason_15 / fail_reason_30: distinct reasons of every failing direction and period, sorted, joined with "; ".
-- span_*: from route_span; express_pass: from express_peak_trips, weekday express routes with service only.
create or replace table route_compliance as
with period_rollup as (
    select
        feed_version, date, route_short_name,
        bool_and(passes_15) as tier_15_pass,
        bool_and(passes_30) as tier_30_pass,
        nullif(array_to_string(list_sort(list(distinct reason_15) filter (where reason_15 is not null)), '; '), '')
            as fail_reason_15,
        nullif(array_to_string(list_sort(list(distinct reason_30) filter (where reason_30 is not null)), '; '), '')
            as fail_reason_30
    from route_period_headway
    group by feed_version, date, route_short_name
),
weakest as (
    select feed_version, date, route_short_name, direction_id, period, headway_median_s
    from route_period_headway
    where category = 'bus' and (covers_30 or period = 'weekend_day')
    qualify row_number() over (
        partition by feed_version, date, route_short_name
        order by headway_median_s is not null, headway_median_s desc, direction_id, period
    ) = 1
),
express as (
    select feed_version, date, route_short_name, bool_and(passes) as express_pass
    from express_peak_trips
    group by feed_version, date, route_short_name
),
trips as (
    select feed_version, date, route_short_name, count(*) as n_trips
    from active_trips
    group by feed_version, date, route_short_name
)
select
    cd.feed_version,
    cd.date,
    cd.day_type,
    r.route_short_name,
    r.category,
    coalesce(t.n_trips, 0) as n_trips,
    t.n_trips is null as no_service_on_date,
    case
        when t.n_trips is null then 'no service on date'
        when r.is_express then 'not scored (express)'
        when cd.day_type <> 'weekday' then 'report only'
        when p.tier_15_pass then '15-min'
        when p.tier_30_pass then '30-min'
        else 'below standard'
    end as tier,
    p.tier_15_pass,
    p.tier_30_pass,
    p.fail_reason_15,
    p.fail_reason_30,
    w.direction_id as weakest_direction,
    w.period as weakest_period,
    w.headway_median_s as weakest_median_s,
    s.span_applicable,
    s.span_pass,
    s.span_start,
    s.span_end,
    e.express_pass
from comparison_dates cd
join bus_routes r on r.feed_version = cd.feed_version
left join trips t on t.feed_version = cd.feed_version and t.date = cd.date and t.route_short_name = r.route_short_name
left join period_rollup p
    on p.feed_version = cd.feed_version and p.date = cd.date and p.route_short_name = r.route_short_name
left join weakest w on w.feed_version = cd.feed_version and w.date = cd.date and w.route_short_name = r.route_short_name
left join route_span s on s.feed_version = cd.feed_version and s.date = cd.date and s.route_short_name = r.route_short_name
left join express e on e.feed_version = cd.feed_version and e.date = cd.date and e.route_short_name = r.route_short_name;
