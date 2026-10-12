-- seed.sql : sample data. Dates are relative to today so the demo always looks fresh.
-- Run after schema.sql:  mysql -u root -p car_rental_db < seed.sql
USE car_rental_db;

INSERT INTO vehicles (vehicle_id, registration_number, brand, model, vehicle_type, manufacturing_year, fuel_type, transmission_type, seating_capacity, daily_rent, availability_status) VALUES
 (1,'MH12AB1234','Maruti Suzuki','Swift','Hatchback',2022,'Petrol','Manual',5,1800.00,'Available'),
 (2,'MH14CD5678','Hyundai','Creta','SUV',2023,'Diesel','Automatic',5,3200.00,'Rented'),
 (3,'MH12EF9012','Honda','City','Sedan',2021,'Petrol','Automatic',5,2600.00,'Available'),
 (4,'KA01GH3456','Toyota','Innova Crysta','MUV',2022,'Diesel','Manual',7,4200.00,'Rented'),
 (5,'MH20JK7890','Tata','Nexon EV','SUV',2023,'Electric','Automatic',5,3000.00,'Available'),
 (6,'DL3CAB2468','Mahindra','Thar','SUV',2022,'Diesel','Manual',4,3800.00,'Maintenance'),
 (7,'MH43LM1357','Kia','Seltos','SUV',2023,'Petrol','Automatic',5,3400.00,'Available'),
 (8,'GJ05NP9753','Maruti Suzuki','Dzire','Sedan',2021,'CNG','Manual',5,2000.00,'Available');

INSERT INTO customers (customer_id, full_name, phone, email, driving_license_number, address) VALUES
 (1,'Aarav Sharma','9876543210','aarav.sharma@example.com','MH1220190012345','12 Residency Road, Pune'),
 (2,'Priya Nair','9123456780','priya.nair@example.com','KL0720180054321','45 MG Road, Kochi'),
 (3,'Rohan Mehta','9988776655','rohan.mehta@example.com','GJ0120200098765','8 CG Road, Ahmedabad'),
 (4,'Sneha Iyer','9012345678','sneha.iyer@example.com','TN0920170076543','23 Anna Nagar, Chennai'),
 (5,'Vikram Singh','9811122233','vikram.singh@example.com','DL0420210034567','77 Lajpat Nagar, New Delhi'),
 (6,'Ananya Reddy','9700011122','ananya.reddy@example.com','TS0820190023456','5 Jubilee Hills, Hyderabad'),
 (7,'Karan Patel','9898989898','karan.patel@example.com','GJ0520180087654','31 Alkapuri, Vadodara'),
 (8,'Meera Joshi','9765432101','meera.joshi@example.com','MH1420220065432','9 Kothrud, Pune');

INSERT INTO reservations (reservation_id, customer_id, vehicle_id, booking_date, start_date, expected_return_date, reservation_status, total_estimated_cost) VALUES
 (1,1,2,DATE_SUB(CURDATE(),INTERVAL 10 DAY),DATE_SUB(CURDATE(),INTERVAL 5 DAY),DATE_SUB(CURDATE(),INTERVAL 1 DAY),'Active',12800.00),
 (2,2,4,DATE_SUB(CURDATE(),INTERVAL 6 DAY),DATE_SUB(CURDATE(),INTERVAL 2 DAY),DATE_ADD(CURDATE(),INTERVAL 3 DAY),'Active',21000.00),
 (3,3,1,DATE_SUB(CURDATE(),INTERVAL 25 DAY),DATE_SUB(CURDATE(),INTERVAL 20 DAY),DATE_SUB(CURDATE(),INTERVAL 17 DAY),'Completed',5400.00),
 (4,4,3,DATE_SUB(CURDATE(),INTERVAL 20 DAY),DATE_SUB(CURDATE(),INTERVAL 15 DAY),DATE_SUB(CURDATE(),INTERVAL 12 DAY),'Completed',7800.00),
 (5,5,5,DATE_SUB(CURDATE(),INTERVAL 16 DAY),DATE_SUB(CURDATE(),INTERVAL 12 DAY),DATE_SUB(CURDATE(),INTERVAL 9 DAY),'Completed',9000.00),
 (6,6,7,DATE_SUB(CURDATE(),INTERVAL 12 DAY),DATE_SUB(CURDATE(),INTERVAL 8 DAY),DATE_SUB(CURDATE(),INTERVAL 6 DAY),'Completed',6800.00),
 (7,7,8,DATE_SUB(CURDATE(),INTERVAL 35 DAY),DATE_SUB(CURDATE(),INTERVAL 30 DAY),DATE_SUB(CURDATE(),INTERVAL 28 DAY),'Cancelled',4000.00),
 (8,1,1,DATE_SUB(CURDATE(),INTERVAL 2 DAY),CURDATE(),DATE_ADD(CURDATE(),INTERVAL 3 DAY),'Confirmed',5400.00),
 (9,8,3,CURDATE(),DATE_ADD(CURDATE(),INTERVAL 2 DAY),DATE_ADD(CURDATE(),INTERVAL 5 DAY),'Confirmed',7800.00),
 (10,3,5,CURDATE(),DATE_ADD(CURDATE(),INTERVAL 7 DAY),DATE_ADD(CURDATE(),INTERVAL 10 DAY),'Confirmed',9000.00),
 (11,2,7,CURDATE(),DATE_ADD(CURDATE(),INTERVAL 1 DAY),DATE_ADD(CURDATE(),INTERVAL 4 DAY),'Confirmed',10200.00);

INSERT INTO rentals (rental_id, reservation_id, actual_pickup_datetime, actual_return_datetime, pickup_odometer, return_odometer, pickup_condition, return_condition, rental_charge, fuel_charge, damage_charge, other_charge, late_fee, final_amount, rental_status) VALUES
 (1,3,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 20 DAY),'10:00:00'),TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 17 DAY),'09:30:00'),15000,15420,'Good','Good',5400.00,0,0,0,0,5400.00,'Returned'),
 (2,4,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 15 DAY),'11:00:00'),TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 12 DAY),'10:00:00'),30100,30650,'Excellent','Good',7800.00,500.00,0,0,0,8300.00,'Returned'),
 (3,5,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 12 DAY),'09:00:00'),TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 9 DAY),'09:00:00'),8200,8760,'Excellent','Good',9000.00,0,0,0,0,9000.00,'Returned'),
 (4,6,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 8 DAY),'10:00:00'),TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 5 DAY),'08:00:00'),12000,12640,'Good','Fair',10200.00,0,800.00,0,1700.00,12700.00,'Returned');
INSERT INTO rentals (rental_id, reservation_id, actual_pickup_datetime, pickup_odometer, pickup_condition, rental_status) VALUES
 (5,1,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 5 DAY),'10:00:00'),24500,'Good','Active'),
 (6,2,TIMESTAMP(DATE_SUB(CURDATE(),INTERVAL 2 DAY),'09:30:00'),41200,'Excellent','Active');
