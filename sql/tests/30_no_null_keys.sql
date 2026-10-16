-- test: no key column of any mart is NULL
-- Offending rows: the table and how many rows have a NULL in a key column.
select 'route_period_headway' as tbl, count(*) as rows_with_null_key
from route_period_headway
where feed_version is null or date is null or route_short_name is null or direction_id is null or period is null
having count(*) > 0
union all
select 'route_span', count(*)
from route_span
where feed_version is null or date is null or route_short_name is null
having count(*) > 0
union all
select 'express_peak_trips', count(*)
from express_peak_trips
where feed_version is null or date is null or route_short_name is null or period is null
having count(*) > 0
union all
select 'route_compliance', count(*)
from route_compliance
where feed_version is null or date is null or route_short_name is null or tier is null
having count(*) > 0
union all
select 'before_after_headway', count(*)
from before_after_headway
where day_type is null or route_short_name is null or direction_id is null or period is null
having count(*) > 0
union all
select 'before_after', count(*)
from before_after
where route_short_name is null or tier_before is null or tier_after is null or change is null
having count(*) > 0;
