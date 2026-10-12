# Likely Viva Questions

1. **What is the project?** A web application on Flask + MySQL that manages vehicles, customers, reservations, vehicle pickup and
   return with billing.
2. **Why MySQL?** A relational DBMS with transactions (InnoDB), foreign keys, CHECK constraints (8.0.16+) and triggers.
3. **Tables?** vehicles, customers, reservations, rentals, and a small settings table for the late-fee policy.
4. **Primary keys / foreign keys?** Auto-increment ids. reservations -> customers, reservations -> vehicles, rentals -> reservations.
5. **Cardinality?** Customer 1:N reservations; vehicle 1:N reservations; reservation 1:0..1 rental.
6. **Which normal form?** 3NF: no repeated customer/vehicle data, no partial or transitive dependencies. Prices are stored as snapshots on purpose.
7. **Why store total_estimated_cost and final_amount if derivable?** Rates can change; a past bill must stay the same.
8. **How do you prevent overlapping bookings?** In one transaction the vehicle row is locked (`FOR UPDATE`), then we look for an
   active reservation with `start < new_end AND end > new_start`. Back-to-back dates are allowed.
9. **Why does a future booking not make a vehicle unavailable today?** Availability for a booking is decided by date overlap; the status flag only says Available / Rented / Maintenance now.
10. **What is a transaction? Where used?** A group of statements that all succeed or all roll back. Used in start rental (insert rental + update reservation + update vehicle) and return.
11. **ACID?** Atomicity, Consistency, Isolation, Durability.
12. **How is a double return prevented?** The rental row is locked and its status must be `Active`; after return it is `Returned`.
13. **How is a duplicate active rental prevented?** App check, plus a BEFORE INSERT trigger on rentals.
14. **How is late fee calculated?** After end of expected return date + 2 grace hours, each late day = daily rent x 50%. Values come from the `settings` table.
15. **SQL injection?** All queries use parameters (`%s`), never string concatenation of user input.
16. **CSRF?** A random token stored in the session must match a hidden form field on every POST.
17. **Why can a vehicle with history not be deleted?** Foreign keys use RESTRICT and the app checks first, so history stays correct.
18. **What is the difference between WHERE and HAVING?** WHERE filters rows before grouping; HAVING filters groups after aggregation.
19. **INNER vs LEFT JOIN?** INNER returns matching rows only; LEFT keeps all left rows (customers with no bookings still show).
20. **Why indexes?** Faster search and overlap checks, for example on (vehicle_id, start_date, expected_return_date).
21. **What happens when a vehicle is returned Damaged?** It goes to Maintenance, so it cannot be booked until edited back to Available.
22. **Which constraints exist?** NOT NULL, UNIQUE, CHECK, DEFAULT, PRIMARY KEY, FOREIGN KEY.
