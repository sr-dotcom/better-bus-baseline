create or replace view stg_agency as
select * exclude (loaded_at_utc)
from raw_agency;
