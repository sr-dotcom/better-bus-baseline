# MPTA-04 (formerly MTC-06) Transit Service Guidelines: sections used by the metrics

Policy MTC-06, "Transit Service Guidelines", approved by the Metropolitan Transit Commission, responsible division CATS Operations. This file quotes only the sections the metrics rely on. The PDF is not stored in this repository; fetch it from the URL below and check the SHA-256.

## Source

| Item | Value |
| --- | --- |
| URL | `https://www.charlottenc.gov/files/sharedassets/cats/v/1/mtc-policies/mtc-06_transit_service_guidelines[1].pdf` |
| Downloaded (UTC) | 2026-10-16T16:47:30Z |
| SHA-256 | `421b791c18a87867a7b056ff44a9375f0d09dc68bd014f991dd02b79e7e17038` |
| Size | 332,038 bytes, 15 pages |
| Date approved | July 26, 2023 (page 1 header, repeated on every page) |
| Previous revision | November 28, 2018 (page 15) |

Page numbers below are the PDF's own "Page Number: N of 15" header, which matches the PDF page index. Section numbers are the PDF's own. The text was extracted with `pdftotext -layout`. Quotes are verbatim, including the PDF's typographical errors (marked [sic]). The PDF's bullet symbols do not extract as text; they are shown here as "-".

## Current policy number: MPTA-04

CATS now publishes the same Transit Service Guidelines as MPTA-04. The quotes in this file are from the MTC-06 PDF above and keep their clause numbers.

| Item | Value |
| --- | --- |
| Named on | `https://www.charlottenc.gov/CATS/Plans-Projects/Service-Change` ("The CATS Transit Service Guidelines (MPTA-04)") |
| URL | `https://mpta.granicus.com/DocumentViewer.php?file=mpta_0b4ad2892ad5de1c5a7bde67b65bd0d8.pdf&view=1` |
| Downloaded (UTC) | 2026-10-16T19:51:01Z |
| SHA-256 | `e53f29b45b33b763b94620cfc259d4e5998ec51fba45d6599bf44867d5c8e5e2` |
| Size | 213,888 bytes, 12 pages |
| Effective date | July 1, 2026 (approved by the MPTA Board of Trustees) |

Sections 3.3 and 3.7 were compared with the text quoted here. Section 3.7 is word for word the same (after whitespace is normalised, the only difference is a line break inside "off-peak"). Section 3.3 is the same apart from one corrected typo ("andremedial" is correct in MPTA-04) and one added sentence on rail ("CATS will monitor Rail services for on-time performance. ..."). Details in `mpta04.md`.

## Approval date (page 1)

> Approved by: Metropolitan Transit Commission    Date Approved: July 26, 2023

## Section 2.4 Service Modes, route categories (page 3)

The section is titled "Service Modes"; the route categories are in its fourth paragraph.

> The fixed route bus network includes specifically numbered bus routes that pick up
> and drop off passengers at regularly scheduled stops and intervals along a defined
> route. Bus routes are broken down into four categories based on service type and
> frequency:
>
> - High Frequency Bus Routes - Frequent bus routes that have a minimum
>   headway of 15-minutes or better
>
> - Common / Local Routes - Bus routes that provide all day service on
>   weekdays and weekends
>
> - Neighborhood / Connector Routes - Feeder routes that provide neighborhood
>   connections to other fixed routes within the CATS network
>
> - Express Routes - Peak hour, weekday only commuter routes that typically
>   provide limited stop service between two key destinations

## Section 3.3 On-Time Performance (page 9)

> To ensure that transit riders have confidence that the service will perform reliably in
> accordance with the public timetables prepared and distributed by CATS, on-time
> performance standards have been established. A vehicle is considered "late" when
> it arrives five minutes or more after the scheduled time. A vehicle is considered
> "early" if ii [sic] departs one minute or more prior to the scheduled time. All other trips
> are considered "on time".
>
> - On-Time Performance: CATS bus routes that achieve an on-time
>   performance score of 80 percent or less over a course of two service changes
>   will be reviewed andremedial [sic] action to improve performance will be put in
>   place at the next service change.

Reading used by the metrics: the trigger is a score of 80 percent or less (80.0 itself triggers a review), and it is judged over two service changes.

## Section 3.7 Service Frequency and Span (page 11)

> Service frequency is established to provide a sufficient number of vehicles to
> accommodate passenger volume at the most crowded location(s), during a given
> time period. On high ridership routes, the frequency of service provided is a function
> of demand and peak period loads. Frequency of service provided is also a function
> of Operator and vehicle availability. Service span refers to the hours that service is
> provided and defines the minimum period of time that service will operate at any
> point in the system.
>
> Headways/ Frequency: As resources become available, CATS will strive to provide
> at least 15-minute peak service on high frequency routes and at least 30-minute
> service on Common/local routes and Neighborhood / Connector routes. Express
> and Regional Express services will have a minimum of three trips in each peak
> direction. For light rail services, CATS will strive to operate at a frequency of 7.5
> minutes or better during the peak periods and at least 30 minutes during the off-
> peak periods. Streetcar service will operate a frequency of 15 minutes or better
> during peak periods and at least 30 minutes during off-peak periods.
>
> Service Span: CATS Fixed Route Services will operate between 5:00 a.m. and
> 1:30 a.m.
>
> Exceptions will be based on ridership and productivity.

## Gaps in the policy

Both gaps were checked against the full extracted text of all 15 pages (search for peak, off-peak, weekend, Saturday, Sunday, weekday, a.m., p.m., hours).

1. **No peak hours are defined.** "Peak" appears in sections 2.4, 3.2 (load tables: "Peak Hour Service") and 3.7 ("peak service", "peak period loads", "each peak direction", "peak periods"), but no clock times or day types define when a peak starts or ends. The only clock times in the document are the service span in 3.7 (5:00 a.m. to 1:30 a.m.). Any peak window used in an analysis is therefore an assumption of the analysis, not a policy value.
2. **No weekend frequency standard exists.** Section 3.7 sets headway targets for peak and (for rail and streetcar) off-peak periods only. Section 2.4 says Common / Local routes provide service on weekdays and weekends, but no section gives a Saturday or Sunday headway. The word "weekend" appears once (section 2.4) and "Saturday" and "Sunday" never appear.

Two further limits on reading 3.7: the headway and span wording is a goal ("will strive"), not a hard standard, and it carries the exception "based on ridership and productivity". The page-1 header states that printed copies are uncontrolled.
