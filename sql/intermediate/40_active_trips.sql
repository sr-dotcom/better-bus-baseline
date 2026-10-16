-- Trips that run on each comparison date, bus routes only. Service comes from calendar_dates only, as in
-- ingest/calendar.py: a service_id runs on a date when it has an exception_type 1 row and no exception_type 2 row.
create or replace table active_trips as
with active_services as (
    select distinct cd.feed_version, cd.date, c.service_id
    from comparison_dates cd
    join stg_calendar_dates c on c.feed_version = cd.feed_version and c.date = cd.date
    where c.exception_type = 1
      and not exists (
          select 1
          from stg_calendar_dates x
          where x.feed_version = c.feed_version and x.date = c.date
            and x.service_id = c.service_id and x.exception_type = 2
      )
)
select
    a.feed_version,
    a.date,
    cd.day_type,
    t.trip_id,
    r.route_short_name,
    t.direction_id
from active_services a
join comparison_dates cd on cd.feed_version = a.feed_version and cd.date = a.date
join stg_trips t on t.feed_version = a.feed_version and t.service_id = a.service_id
join bus_routes r on r.feed_version = t.feed_version and r.route_id = t.route_id;
