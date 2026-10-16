create or replace view stg_shapes as
select * exclude (loaded_at_utc) replace (
    cast(shape_pt_lat as double) as shape_pt_lat,
    cast(shape_pt_lon as double) as shape_pt_lon,
    cast(shape_pt_sequence as integer) as shape_pt_sequence
)
from raw_shapes;
