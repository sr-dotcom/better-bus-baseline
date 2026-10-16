-- test: every non-empty raw stop time parses to seconds in staging, and every trip has its first and last stop times
-- Offending rows: the column and how many values failed.
select 'arrival_time did not parse' as problem, count(*) as n
from raw_stop_times
where arrival_time <> '' and gtfs_seconds(arrival_time) is null
having count(*) > 0
union all
select 'departure_time did not parse', count(*)
from raw_stop_times
where departure_time <> '' and gtfs_seconds(departure_time) is null
having count(*) > 0
union all
select 'first stop has no departure time', count(*)
from first_stop_departures
where departure_s is null
having count(*) > 0
union all
select 'last stop has no arrival time', count(*)
from last_stop_arrivals
where arrival_s is null
having count(*) > 0
union all
select 'stop_sequence repeats within a trip', count(*)
from (
    select feed_version, trip_id
    from stg_stop_times
    group by feed_version, trip_id
    having count(*) <> count(distinct stop_sequence)
)
having count(*) > 0;
