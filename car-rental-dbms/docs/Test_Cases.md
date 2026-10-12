# Test Cases

"Actual result" is filled only for checks that were really executed. Automated tests: `tests/test_app.py` run with pytest
against a real MySQL 8.0 server (11 tests, all passed on 12 Oct 2026). Queries in `queries.sql` ran without errors.
Not executed in the build environment: checks in a real browser (layout, JavaScript cost estimate, print dialog).

| # | Test | Expected result | Actual result |
|---|---|---|---|
| 1 | Open all pages and all 8 reports (HTTP GET) | HTTP 200 | Passed (automated) |
| 2 | Dashboard counts vs database | 8 vehicles, 2 active rentals, 1 overdue | Passed (automated) |
| 3 | POST without CSRF token | HTTP 400 | Passed (automated) |
| 4 | Add vehicle, duplicate registration, negative rent | Added; duplicate and invalid rejected with message | Passed (automated) |
| 5 | Edit vehicle, delete unused vehicle, delete vehicle with history | Updated; deleted; deletion refused | Passed (automated) |
| 6 | Add/edit/delete customer, duplicate phone, bad phone, search | Saved; duplicate/invalid rejected; search filters | Passed (automated) |
| 7 | Reservation overlapping existing booking (inside and partial) | Rejected "already reserved" | Passed (automated) |
| 8 | Return date = start date; start date in past; vehicle in maintenance | Rejected with message | Passed (automated) |
| 9 | Back-to-back and non-overlapping bookings; estimate 2 days x 3000 | Created; cost 6000.00 | Passed (automated) |
| 10 | Edit reservation, cancel, cancel again, rebook cancelled dates | Updated; Cancelled; second cancel refused; dates free again | Passed (automated) |
| 11 | Pickup with low odometer / future time / wrong status | Rejected | Passed (automated) |
| 12 | Start rental from Confirmed reservation | Rental Active, reservation Active, vehicle Rented | Passed (automated) |
| 13 | Start same reservation again; trigger inserting a 2nd active rental | App refuses; trigger raises error | Passed (automated) |
| 14 | Late-fee/billing function with fixed dates (on time, in grace, 6 h late, 3 late days, same day) | 2000; 2000; 3500; 6650; 1 day | Passed (automated) |
| 15 | Return with low odometer, non-numeric/3-decimal charge, future time | Rejected | Passed (automated) |
| 16 | Preview bill then complete return (4 days x 3200 + 300 fuel) | Preview saves nothing; saved final 13100.00; vehicle Available; reservation Completed | Passed (automated) |
| 17 | Return same rental twice | Second attempt rejected | Passed (automated) |
| 18 | Return as Damaged without damage charge, then with 1500 | Rejected, then saved 5700.00; vehicle Maintenance | Passed (automated) |
| 19 | Revenue report total and customer-history filter, available-vehicle report, invoice | Matches database values | Passed (automated) |
| 20 | schema.sql, seed.sql, queries.sql executed on MySQL 8.0 | No errors; seed data unchanged after queries.sql | Passed (manual run) |
| 21 | Look and feel in a browser, cost estimate script, printing invoice | Pages render consistently | **Not tested - please check locally** |
