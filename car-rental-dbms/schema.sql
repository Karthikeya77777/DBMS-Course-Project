-- ============================================================
-- Car Rental Reservation and Vehicle Return Management System
-- schema.sql : database, tables, constraints, indexes, trigger
-- Run:  mysql -u root -p < schema.sql
-- WARNING: DROP TABLE statements below reset the database.
-- ============================================================
CREATE DATABASE IF NOT EXISTS car_rental_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE car_rental_db;

DROP TABLE IF EXISTS rentals;
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS settings;

-- Rental policy values (late fee etc.) live here so they are configurable, not hard-coded.
CREATE TABLE settings (
    setting_key   VARCHAR(40)  NOT NULL PRIMARY KEY,
    setting_value DECIMAL(10,2) NOT NULL,
    description   VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE vehicles (
    vehicle_id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    registration_number VARCHAR(20)  NOT NULL,
    brand               VARCHAR(50)  NOT NULL,
    model               VARCHAR(50)  NOT NULL,
    vehicle_type        ENUM('Hatchback','Sedan','SUV','MUV','Convertible','Van') NOT NULL,
    manufacturing_year  SMALLINT UNSIGNED NOT NULL,
    fuel_type           ENUM('Petrol','Diesel','Electric','CNG','Hybrid') NOT NULL,
    transmission_type   ENUM('Manual','Automatic') NOT NULL,
    seating_capacity    TINYINT UNSIGNED NOT NULL,
    daily_rent          DECIMAL(10,2) NOT NULL,
    availability_status ENUM('Available','Rented','Maintenance') NOT NULL DEFAULT 'Available',
    CONSTRAINT uq_vehicle_registration UNIQUE (registration_number),
    CONSTRAINT chk_vehicle_year   CHECK (manufacturing_year BETWEEN 1990 AND 2100),
    CONSTRAINT chk_vehicle_seats  CHECK (seating_capacity BETWEEN 1 AND 20),
    CONSTRAINT chk_vehicle_rent   CHECK (daily_rent > 0),
    INDEX idx_vehicle_status (availability_status),
    INDEX idx_vehicle_type (vehicle_type),
    INDEX idx_vehicle_brand_model (brand, model)
) ENGINE=InnoDB;

CREATE TABLE customers (
    customer_id            INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    full_name              VARCHAR(100) NOT NULL,
    phone                  VARCHAR(15)  NOT NULL,
    email                  VARCHAR(120) NOT NULL,
    driving_license_number VARCHAR(30)  NOT NULL,
    address                VARCHAR(255) NOT NULL,
    CONSTRAINT uq_customer_phone   UNIQUE (phone),
    CONSTRAINT uq_customer_email   UNIQUE (email),
    CONSTRAINT uq_customer_license UNIQUE (driving_license_number),
    INDEX idx_customer_name (full_name)
) ENGINE=InnoDB;

CREATE TABLE reservations (
    reservation_id       INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id          INT UNSIGNED NOT NULL,
    vehicle_id           INT UNSIGNED NOT NULL,
    booking_date         DATE NOT NULL DEFAULT (CURRENT_DATE),
    start_date           DATE NOT NULL,
    expected_return_date DATE NOT NULL,
    reservation_status   ENUM('Confirmed','Active','Completed','Cancelled') NOT NULL DEFAULT 'Confirmed',
    total_estimated_cost DECIMAL(10,2) NOT NULL,
    CONSTRAINT fk_res_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_res_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_res_dates CHECK (expected_return_date > start_date),
    CONSTRAINT chk_res_cost  CHECK (total_estimated_cost >= 0),
    INDEX idx_res_vehicle_dates (vehicle_id, start_date, expected_return_date),
    INDEX idx_res_customer (customer_id),
    INDEX idx_res_status (reservation_status),
    INDEX idx_res_start (start_date)
) ENGINE=InnoDB;

CREATE TABLE rentals (
    rental_id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    reservation_id        INT UNSIGNED NOT NULL,
    actual_pickup_datetime DATETIME NOT NULL,
    actual_return_datetime DATETIME NULL,
    pickup_odometer       INT UNSIGNED NOT NULL,
    return_odometer       INT UNSIGNED NULL,
    pickup_condition      ENUM('Excellent','Good','Fair','Damaged') NOT NULL,
    return_condition      ENUM('Excellent','Good','Fair','Damaged') NULL,
    rental_charge         DECIMAL(10,2) NULL,
    fuel_charge           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    damage_charge         DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    other_charge          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    late_fee              DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    final_amount          DECIMAL(10,2) NULL,
    rental_status         ENUM('Active','Returned') NOT NULL DEFAULT 'Active',
    CONSTRAINT uq_rental_reservation UNIQUE (reservation_id),  -- one rental per reservation
    CONSTRAINT fk_rental_reservation FOREIGN KEY (reservation_id) REFERENCES reservations(reservation_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT chk_rental_odometer CHECK (return_odometer IS NULL OR return_odometer >= pickup_odometer),
    CONSTRAINT chk_rental_charges  CHECK (fuel_charge >= 0 AND damage_charge >= 0 AND other_charge >= 0 AND late_fee >= 0),
    CONSTRAINT chk_rental_state CHECK (
        (rental_status = 'Active'   AND actual_return_datetime IS NULL AND final_amount IS NULL) OR
        (rental_status = 'Returned' AND actual_return_datetime IS NOT NULL AND final_amount IS NOT NULL)),
    INDEX idx_rental_status (rental_status),
    INDEX idx_rental_return (actual_return_datetime)
) ENGINE=InnoDB;

-- Safety net: a vehicle can never have two active rentals at once (the app checks this too).
DROP TRIGGER IF EXISTS trg_rentals_one_active_per_vehicle;
DELIMITER //
CREATE TRIGGER trg_rentals_one_active_per_vehicle BEFORE INSERT ON rentals
FOR EACH ROW
BEGIN
    IF NEW.rental_status = 'Active' AND EXISTS (
        SELECT 1 FROM rentals rt
        JOIN reservations r ON r.reservation_id = rt.reservation_id
        WHERE rt.rental_status = 'Active'
          AND r.vehicle_id = (SELECT vehicle_id FROM reservations WHERE reservation_id = NEW.reservation_id)
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'This vehicle already has an active rental';
    END IF;
END//
DELIMITER ;

-- Essential initial data: rental policy
INSERT INTO settings (setting_key, setting_value, description) VALUES
 ('late_grace_hours',  2.00,     'Hours after the end of the expected return date before late fees start'),
 ('late_fee_percent',  50.00,    'Late fee per late day, as a percentage of the vehicle daily rent (charged on top of normal rent)'),
 ('max_extra_charge',  100000.00,'Largest value accepted for any single fuel/damage/other charge');
