create or replace view stg_routes as
select * exclude (loaded_at_utc) replace (cast(route_type as integer) as route_type)
from raw_routes;
