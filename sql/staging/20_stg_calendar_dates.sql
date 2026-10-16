-- Service days. Neither feed has calendar.txt, so this table alone says when a service_id runs.
create or replace view stg_calendar_dates as
select
    feed_version,
    service_id,
    strptime(date, '%Y%m%d')::date as date,
    cast(exception_type as integer) as exception_type
from raw_calendar_dates;
