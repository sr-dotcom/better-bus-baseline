create or replace view stg_trips as
select * exclude (loaded_at_utc) replace (cast(nullif(direction_id, '') as integer) as direction_id)
from raw_trips;
