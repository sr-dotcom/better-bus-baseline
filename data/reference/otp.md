# On-time performance context (published system figure)

Context only. The audit in this repository scores the published schedule (GTFS), not delivered service. This file records the latest bus on-time performance figure that CATS published in a public board packet, so a reader can see how the schedule findings sit next to the system figure. It is not a route score and it does not feed any tier.

## The figure

| Item | Value |
| --- | --- |
| Measure | Bus on-time performance, system-wide (all bus routes together) |
| Value | 85% |
| Month | August 2026 |
| Same month, prior year | 84% (+1 point, as printed in the packet) |
| Source | MPTA Board of Trustees Business Meeting packet of October 14, 2026, attachment "CATS Monthly Performance Reports (August 2026)", Bus Service Performance Report - August 2026 |
| URL | `https://mpta.granicus.com/AgendaViewer.php?view_id=5&clip_id=290` (redirects to the packet PDF on the MPTA Granicus site) |
| Page | PDF page 102 of 119 (the figure is in the "On-Time Performance" row of the bus table); the same 85% is repeated in the "Service Delivery & Reliability Summary" table on PDF page 108 |
| Definition | PDF page 101: a delivered timepoint is on-time when departure is no more than one minute early or five minutes late. Cancelled or otherwise undelivered service is not in the OTP calculation (it is in the separate Service Delivered measure) |
| Retrieved (UTC) | 2026-10-16T19:44:30Z |
| SHA-256 of the packet PDF | `2bdd8c4be8330ef3cae0aacd6cb33f342fceaf3b189a0d7e6455578e16c2dc0b` (5,491,831 bytes; not stored in this repository) |

The page numbers are PDF page indexes of the downloaded file (text extracted with `pdftotext -layout`; pages are separated by form feeds). The packet carries no printed page numbers on these pages.

## How the packet was found

The CATS "Boards and Committees" page links to RideMPTA.com and to the MPTA Granicus site. The Granicus archive list (`https://mpta.granicus.com/ViewPublisher.php?view_id=5`) names the Business Meeting of Oct 14, 2026 as its newest entry; its Agenda link is the packet PDF. The earlier Aug 12, 2026 packet (June 2026 report) gives bus OTP of 86% for June 2026, an OTP goal of 85% ("This exceeded the OTP goal of 85%"), and a 13-month system series under a chart titled "Bus Route On Time Performance" that is a single system series, not a series per route. August 2026 is the latest month found, not the only one published.

## Limits

- It is one system-wide figure, not a route figure. MTC-06 3.3 applies its 80 percent trigger to each bus route ("CATS bus routes that achieve an on-time performance score of 80 percent or less over a course of two service changes"). The two packets checked (Aug 12 and Oct 14, 2026) give no route-level OTP in any month, so the per-route test cannot be run from public data.
- The packet's on-time window (one minute early to five minutes late) is not worded identically to MTC-06 3.3, which calls a vehicle late "when it arrives five minutes or more after the scheduled time".
- It is a single month. MTC-06 3.3 looks over two service changes.
- A system figure of 85% can sit above 80% while individual routes sit below it. The figure says nothing about the routes this audit scores.
- The figure is the agency's own, from its own data. This repository did not verify it.

## Gap

No route-level OTP is published. This is a finding in itself: the policy sets a per-route trigger that the public cannot check.
