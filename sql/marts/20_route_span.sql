-- Span of service per route and date, over all active trips in both directions. One row per feed_version, date,
-- route that has at least one active trip (a route with none has no span; route_compliance reports it as no service).
-- first_departure_s: earliest first-stop departure. last_arrival_s: latest last-stop arrival (may pass 86400).
-- span_start / span_end: the same as HH:MM:SS, hours past 24 kept (25:52:00 is 01:52 the next morning).
-- span_applicable: false for express routes (MTC-06 2.4: peak hour, weekday only commuter routes).
-- span_pass: MTC-06 3.7 "between 5:00 a.m. and 1:30 a.m.": start <= 05:00:00 and end >= 25:30:00. NULL when not
--   applicable.
create or replace table route_span as
with first_dep as (
    select feed_version, date, day_type, route_short_name, count(*) as n_trips, min(departure_s) as first_departure_s
    from first_stop_departures
    group by feed_version, date, day_type, route_short_name
),
last_arr as (
    select feed_version, date, route_short_name, max(arrival_s) as last_arrival_s
    from last_stop_arrivals
    group by feed_version, date, route_short_name
)
select
    f.feed_version, f.date, f.day_type, f.route_short_name, r.category,
    f.n_trips,
    f.first_departure_s,
    l.last_arrival_s,
    gtfs_hms(f.first_departure_s) as span_start,
    gtfs_hms(l.last_arrival_s) as span_end,
    not r.is_express as span_applicable,
    case when not r.is_express then f.first_departure_s <= 18000 and l.last_arrival_s >= 91800 end as span_pass
from first_dep f
join last_arr l
    on l.feed_version = f.feed_version and l.date = f.date and l.route_short_name = f.route_short_name
join bus_routes r on r.feed_version = f.feed_version and r.route_short_name = f.route_short_name;
