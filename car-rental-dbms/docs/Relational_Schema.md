# Relational Schema and Normalization Notes

Underlined = primary key; (FK) = foreign key. Types are shown in `schema.sql`.

```
VEHICLE(vehicle_id, registration_number*, brand, model, vehicle_type, manufacturing_year, fuel_type,
        transmission_type, seating_capacity, daily_rent, availability_status)
CUSTOMER(customer_id, full_name, phone*, email*, driving_license_number*, address)
RESERVATION(reservation_id, customer_id (FK), vehicle_id (FK), booking_date, start_date, expected_return_date,
            reservation_status, total_estimated_cost)
RENTAL(rental_id, reservation_id (FK, UNIQUE), actual_pickup_datetime, actual_return_datetime, pickup_odometer,
       return_odometer, pickup_condition, return_condition, rental_charge, fuel_charge, damage_charge, other_charge,
       late_fee, final_amount, rental_status)
SETTINGS(setting_key, setting_value, description)          * = UNIQUE
```
Primary keys: vehicle_id, customer_id, reservation_id, rental_id, setting_key.

## Relationships and cardinality
| Relationship | Cardinality | Delete policy |
|---|---|---|
| CUSTOMER makes RESERVATION | 1 : N | RESTRICT (history preserved) |
| VEHICLE is booked in RESERVATION | 1 : N | RESTRICT |
| RESERVATION becomes RENTAL | 1 : 0..1 (UNIQUE reservation_id) | RESTRICT |
Updates of keys cascade (ON UPDATE CASCADE). The ER diagram is `docs/ER_Diagram.png`.

## Constraints
NOT NULL on mandatory columns; UNIQUE on registration number, phone, email, licence number; CHECK: year range, seats 1-20,
daily_rent > 0, `expected_return_date > start_date`, estimated cost >= 0, return odometer >= pickup odometer, charges >= 0,
and a rental-state check (Active rentals have no return data; Returned rentals have a return time and final amount).
Defaults: availability 'Available', reservation 'Confirmed', rental 'Active', charges 0, booking_date = today.
Indexes: status, type, brand+model, customer name, (vehicle_id, start_date, expected_return_date) for the overlap check,
reservation status/start date, rental status/return time.
Trigger `trg_rentals_one_active_per_vehicle`: blocks a second Active rental for the same vehicle.

## Normalization
* **1NF** - every column holds one atomic value; no repeating groups (one row per reservation, one per rental).
* **2NF** - every table has a single-column primary key, so no partial dependencies exist.
* **3NF** - non-key attributes depend only on their own table's key. Customer details are not repeated in reservations,
  vehicle details are not repeated in reservations, and rental rows do not store customer or vehicle (they are reached
  through `reservation_id`). The `settings` table keeps policy values out of the code.
* **Deliberate stored values** (documented decisions): `total_estimated_cost` and the bill columns (`rental_charge`,
  `late_fee`, `final_amount`...) are snapshots of the price at booking/return time. If `daily_rent` or the policy changes later,
  historical invoices must not change, so they are stored. `final_amount` equals rent + extras + late fee; days, late days
  and total extras are not stored because they can be derived. A separate payments table was not built; the bill is part of the
  rental record.
* `availability_status` on vehicles is an operational flag (Available / Rented / Maintenance). Whether a vehicle can be booked
  for given dates is decided from reservation date overlaps, not from this flag.
