-- Periods are the author's choice: MTC-06 defines no peak hours. Seconds since service-day start, half-open:
-- a departure is in a period when start_s <= departure < end_s, so 09:00:00 is midday and 08:59:59 is AM peak.
-- covers_15: the 15-minute standard is scored here (weekday AM peak and PM peak).
-- covers_30: the 30-minute standard is scored here (weekday AM peak, midday, PM peak).
-- Periods covered by neither (evening, weekend daytime) are reported without a verdict.
-- Must agree with PERIODS in ingest/headway.py (tests/test_sql_marts.py checks it).
create or replace table periods as
select *
from (values
    ('weekday',  'am_peak',     21600, 32400, true,  true,  1),
    ('weekday',  'midday',      32400, 54000, false, true,  2),
    ('weekday',  'pm_peak',     54000, 64800, true,  true,  3),
    ('weekday',  'evening',     64800, 79200, false, false, 4),
    ('saturday', 'weekend_day', 32400, 64800, false, false, 5),
    ('sunday',   'weekend_day', 32400, 64800, false, false, 5)
) as t(day_type, period, start_s, end_s, covers_15, covers_30, sort_order);
