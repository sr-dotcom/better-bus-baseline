-- The six comparison dates (docs/metrics.md). The earlier date of each pair is read from feed 2026-09-10 and the
-- later date from feed 2026-09-29, so each date uses exactly one feed. Same day of the week on both sides.
create or replace table comparison_dates as
select *
from (values
    (date '2026-09-30', '2026-09-10', 'weekday',  'before'),
    (date '2026-10-14', '2026-09-29', 'weekday',  'after'),
    (date '2026-09-26', '2026-09-10', 'saturday', 'before'),
    (date '2026-10-17', '2026-09-29', 'saturday', 'after'),
    (date '2026-09-27', '2026-09-10', 'sunday',   'before'),
    (date '2026-10-18', '2026-09-29', 'sunday',   'after')
) as t(date, feed_version, day_type, side);
