-- test: periods are half-open, and the first and last stop of each trip are the lowest and highest stop_sequence
-- Offending rows: the invariant that failed and how many rows break it.
select 'period departure outside start <= departure < end' as problem, count(*) as n
from period_departures d
join periods p on p.day_type = d.day_type and p.period = d.period
where d.departure_s < p.start_s or d.departure_s >= p.end_s
having count(*) > 0
union all
select 'first-stop departure inside a period but not in period_departures', count(*)
from first_stop_departures f
join periods p on p.day_type = f.day_type
where f.departure_s >= p.start_s and f.departure_s < p.end_s
  and not exists (
      select 1
      from period_departures d
      where d.feed_version = f.feed_version and d.date = f.date and d.trip_id = f.trip_id and d.period = p.period
  )
having count(*) > 0
union all
select 'first stop is not the row with the lowest stop_sequence', count(*)
from first_stop_departures f
join stg_stop_times s on s.feed_version = f.feed_version and s.trip_id = f.trip_id
group by f.feed_version, f.date, f.trip_id, f.stop_sequence, f.stop_id, f.departure_s
having min(s.stop_sequence) <> f.stop_sequence
    or arg_min(s.stop_id, s.stop_sequence) <> f.stop_id
    or arg_min(s.departure_s, s.stop_sequence) <> f.departure_s
union all
select 'last stop is not the row with the highest stop_sequence', count(*)
from last_stop_arrivals l
join stg_stop_times s on s.feed_version = l.feed_version and s.trip_id = l.trip_id
group by l.feed_version, l.date, l.trip_id, l.stop_sequence, l.stop_id, l.arrival_s
having max(s.stop_sequence) <> l.stop_sequence
    or arg_max(s.stop_id, s.stop_sequence) <> l.stop_id
    or arg_max(s.arrival_s, s.stop_sequence) <> l.arrival_s;
