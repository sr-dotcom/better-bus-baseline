-- Helpers shared by every layer. DuckDB macros.

-- GTFS time "H:MM:SS" or "HH:MM:SS" to seconds since the start of the service day (hours may pass 24).
-- Same rule as ingest/gtfs_time.py: anything else gives NULL here (the Python parser raises); the SQL test
-- 10_staging_times.sql fails the build if a non-empty source time turns into NULL.
create or replace macro gtfs_seconds(t) as
    case
        when regexp_full_match(t, '[0-9]{1,2}:[0-5][0-9]:[0-5][0-9]') then
            cast(split_part(t, ':', 1) as integer) * 3600
            + cast(split_part(t, ':', 2) as integer) * 60
            + cast(split_part(t, ':', 3) as integer)
    end;

-- Seconds since service-day start back to HH:MM:SS (hours may pass 24, so 25:52:00 stays 25:52:00).
create or replace macro gtfs_hms(s) as
    lpad(cast(s // 3600 as varchar), 2, '0') || ':' || lpad(cast((s % 3600) // 60 as varchar), 2, '0')
    || ':' || lpad(cast(s % 60 as varchar), 2, '0');
