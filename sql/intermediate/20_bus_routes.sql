-- Bus routes only: route_type 3. Rail (501 and 510, route_type 0) is out of scope.
-- Express: route_short_name ends in "x" (14 routes in both feeds; route_desc is empty and route_type is 3 for all).
create or replace table bus_routes as
select
    feed_version,
    route_id,
    route_short_name,
    route_long_name,
    ends_with(lower(route_short_name), 'x') as is_express,
    case when ends_with(lower(route_short_name), 'x') then 'express' else 'bus' end as category
from stg_routes
where route_type = 3;
