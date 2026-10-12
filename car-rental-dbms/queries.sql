-- ============================================================
-- queries.sql : demonstration queries (run after schema.sql + seed.sql)
-- Run:  mysql -u root -p car_rental_db < queries.sql
-- ============================================================

-- 1. CREATE DATABASE and CREATE TABLE (demo table only, dropped again at the end)
CREATE DATABASE IF NOT EXISTS car_rental_db;
USE car_rental_db;
CREATE TABLE IF NOT EXISTS demo_branch (
    branch_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    city      VARCHAR(60) NOT NULL UNIQUE
);

-- 2. INSERT: add a demo branch and a demo customer
INSERT INTO demo_branch (city) VALUES ('Pune'), ('Mumbai');
INSERT INTO customers (full_name, phone, email, driving_license_number, address)
VALUES ('Demo Customer', '9000011111', 'demo.customer@example.com', 'MH0120230099999', '1 Demo Street, Pune');

-- 3. UPDATE: change the demo customer's phone number and raise one vehicle's daily rent by 5%
UPDATE customers SET phone = '9000022222' WHERE email = 'demo.customer@example.com';
UPDATE vehicles SET daily_rent = ROUND(daily_rent * 1.05, 2) WHERE registration_number = 'MH12AB1234';
UPDATE vehicles SET daily_rent = ROUND(daily_rent / 1.05, 2) WHERE registration_number = 'MH12AB1234'; -- undo (keeps seed data unchanged)

-- 4. DELETE: remove the demo rows (a customer with no reservations can be deleted safely)
DELETE FROM customers WHERE email = 'demo.customer@example.com';
DELETE FROM demo_branch WHERE city = 'Mumbai';

-- 5. SELECT with WHERE and ORDER BY: available SUVs, cheapest first
SELECT vehicle_id, registration_number, brand, model, daily_rent
FROM vehicles
WHERE availability_status = 'Available' AND vehicle_type = 'SUV'
ORDER BY daily_rent ASC;

-- 6. INNER JOIN customers and reservations
SELECT c.full_name, r.reservation_id, r.start_date, r.expected_return_date, r.reservation_status
FROM customers c
INNER JOIN reservations r ON r.customer_id = c.customer_id
ORDER BY c.full_name, r.start_date;

-- 7. JOIN vehicles, reservations and rentals
SELECT v.registration_number, CONCAT(v.brand, ' ', v.model) AS vehicle, r.reservation_id,
       rt.rental_id, rt.actual_pickup_datetime, rt.actual_return_datetime, rt.rental_status
FROM vehicles v
JOIN reservations r ON r.vehicle_id = v.vehicle_id
JOIN rentals rt ON rt.reservation_id = r.reservation_id
ORDER BY rt.actual_pickup_datetime DESC;

-- 8. Aggregate functions: COUNT, SUM, AVG, MIN, MAX over completed rentals
SELECT COUNT(*) AS completed_rentals, SUM(final_amount) AS total_revenue,
       ROUND(AVG(final_amount), 2) AS average_bill, MIN(final_amount) AS smallest_bill, MAX(final_amount) AS largest_bill
FROM rentals WHERE rental_status = 'Returned';

-- 9. GROUP BY and HAVING: vehicle types that have more than one vehicle, with their average daily rent
SELECT vehicle_type, COUNT(*) AS vehicles_in_fleet, ROUND(AVG(daily_rent), 2) AS avg_daily_rent
FROM vehicles
GROUP BY vehicle_type
HAVING COUNT(*) > 1
ORDER BY vehicles_in_fleet DESC;

-- 10. Subquery: vehicles whose daily rent is above the fleet average
SELECT registration_number, brand, model, daily_rent
FROM vehicles
WHERE daily_rent > (SELECT AVG(daily_rent) FROM vehicles)
ORDER BY daily_rent DESC;

-- 11. Overdue rentals: still out although the expected return date has passed
SELECT rt.rental_id, c.full_name, c.phone, v.registration_number, r.expected_return_date,
       DATEDIFF(CURDATE(), r.expected_return_date) AS days_overdue
FROM rentals rt
JOIN reservations r ON r.reservation_id = rt.reservation_id
JOIN customers c ON c.customer_id = r.customer_id
JOIN vehicles v ON v.vehicle_id = r.vehicle_id
WHERE rt.rental_status = 'Active' AND r.expected_return_date < CURDATE()
ORDER BY days_overdue DESC;

-- 12. Total revenue (overall and split into rent, extras and late fees)
SELECT SUM(rental_charge) AS rent, SUM(fuel_charge + damage_charge + other_charge) AS extras,
       SUM(late_fee) AS late_fees, SUM(final_amount) AS total_revenue
FROM rentals WHERE rental_status = 'Returned';

-- 13. Vehicle availability: status now, plus whether a future booking exists
SELECT v.registration_number, CONCAT(v.brand, ' ', v.model) AS vehicle, v.availability_status,
       (SELECT MIN(r.start_date) FROM reservations r
         WHERE r.vehicle_id = v.vehicle_id AND r.reservation_status = 'Confirmed' AND r.start_date >= CURDATE()) AS next_booking_starts
FROM vehicles v
ORDER BY v.availability_status, v.registration_number;

-- 14. Each customer's rental history (customers without bookings still appear thanks to LEFT JOIN)
SELECT c.full_name, COUNT(r.reservation_id) AS reservations, COUNT(rt.rental_id) AS rentals_started,
       COALESCE(SUM(rt.final_amount), 0) AS total_billed
FROM customers c
LEFT JOIN reservations r ON r.customer_id = c.customer_id
LEFT JOIN rentals rt ON rt.reservation_id = r.reservation_id
GROUP BY c.customer_id, c.full_name
ORDER BY total_billed DESC;

-- Clean up the demo table
DROP TABLE IF EXISTS demo_branch;
