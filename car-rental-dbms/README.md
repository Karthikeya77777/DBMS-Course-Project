# DriveDesk - Car Rental Reservation and Vehicle Return Management System

DBMS course project: Flask + MySQL web application with Bootstrap 5 (served locally, no internet needed to run).

## Features
Dashboard (live MySQL statistics) - Vehicles (CRUD, search, filter, details) - Customers (CRUD, search, details) -
Reservations (create, edit, cancel, filters, overlap prevention) - Start rental (pickup with odometer and condition) -
Active rentals - Vehicle return (itemized bill preview, late fee, extra charges) - Return history and printable invoice -
8 reports (reservations, active rentals, available vehicles, returns, overdue, revenue, utilization, customer history).

## Folder structure
```
car-rental-dbms/
  app.py            Flask routes and business rules
  db.py             MySQL connection, query helpers, transaction helper
  schema.sql        database, tables, constraints, indexes, trigger, settings
  seed.sql          sample data (dates are relative to today)
  queries.sql       14 labelled demonstration queries
  requirements.txt  .env.example  .gitignore
  templates/        Jinja2 pages          static/css, static/js, static/vendor (Bootstrap + icons)
  docs/             ER_Diagram.png, Relational_Schema.md, Test_Cases.md, Viva_Questions.md, Screenshots/
  tests/test_app.py automated tests (pytest, real MySQL)
```

## Setup (Windows / macOS / Linux, VS Code terminal)
1. Install Python 3.10+ and MySQL 8.0+ (MySQL must be running; the `mysql` command-line client should be on PATH).
2. Create a virtual environment and install packages:
   ```
   python -m venv venv
   venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
3. Create the database and load the sample data (you will be asked for your MySQL password):
   ```
   mysql -u root -p < schema.sql
   mysql -u root -p car_rental_db < seed.sql
   ```
   `schema.sql` starts with DROP TABLE statements, so re-running it resets the database. Run `seed.sql` again afterwards
   to get fresh demo data (dates are relative to today).
4. Configure credentials: copy `.env.example` to `.env` and put your MySQL user, password and a random SECRET_KEY in it.
   Never commit `.env`.
5. Run: `python app.py` and open **http://127.0.0.1:5000**

Optional: `mysql -u root -p car_rental_db < queries.sql` runs the demonstration queries.

## Rental policy (stored in the `settings` table, editable with SQL)
| Setting | Default | Meaning |
|---|---|---|
| late_grace_hours | 2 | Hours after the end of the expected return date before late fees start |
| late_fee_percent | 50 | Late fee per late day = daily rent x 50% (on top of normal rent) |
| max_extra_charge | 100000 | Upper limit accepted for each fuel / damage / other charge |

* **Rent** = daily rent x calendar days between pickup date and return date (minimum 1 day). A return on time is never billed
  for more days than booked.
* **On time** = returned by 23:59 of the expected return date + grace hours. Each late day or part of a day adds the late fee.
* **Final amount** = rent + late fee + fuel + damage + other charges. The values are saved with the rental, so old invoices do
  not change if rates change later.
* A vehicle returned as *Damaged* goes to **Maintenance** instead of Available.
Change a policy value, for example: `UPDATE settings SET setting_value = 100 WHERE setting_key = 'late_fee_percent';`

## Business rules enforced
Return date after start date - no past start dates - no overlapping Confirmed/Active reservations for a vehicle (back-to-back
bookings are allowed; a future booking does not block the vehicle today) - no reservation for vehicles in Maintenance -
pickup only for Confirmed reservations inside their dates, on an Available vehicle, with odometer not below the last reading -
one active rental per vehicle (app check + database trigger) - no double return - return odometer not below pickup -
vehicles/customers with history cannot be deleted (foreign keys use RESTRICT) - cancelled reservations stay in history.
Pickup/return/reservation changes run inside MySQL transactions with row locks (`SELECT ... FOR UPDATE`).

## Security
Parameterized SQL everywhere, CSRF token on every POST form, server-side validation, credentials only in `.env`.
There is no login screen (the assignment asked for no fake authentication).

## Tests
```
python -m pytest tests -q
```
The tests re-create `car_rental_db` (schema + seed), so use a development database. They need the `mysql` client and the same
`.env` credentials.

## Demo script (2 minutes)
Dashboard -> Reservations: try an overlapping booking (rejected) -> Start rental on the reservation that starts today ->
Active rentals (one rental is already overdue) -> Process return: Preview bill, Complete return -> invoice -> Reports.

## Troubleshooting
* "Database error" page: MySQL is stopped, or `.env` has the wrong user/password/host.
* `Unknown database 'car_rental_db'`: run `schema.sql` first.
* `mysql` not recognized: add the MySQL `bin` folder to PATH, or run the SQL files from MySQL Workbench (File > Run SQL Script).
* Port 5000 busy (macOS AirPlay): `flask --app app run --port 5001`.
* Workbench: use File > Run SQL Script for schema.sql (it contains a trigger written with DELIMITER).

## Screenshots to take (docs/Screenshots/)
Dashboard, vehicle list + add form, customer list + add form, new reservation, active rentals, process return (bill preview),
invoice, reports. They could not be generated in the build environment.

## Prepare for GitHub
```
git init
git add .
git commit -m "Car rental DBMS project"
git branch -M main
git remote add origin https://github.com/<your-username>/car-rental-dbms.git
git push -u origin main
```
Check `git status` first: `.env` and `venv/` must not appear (they are in `.gitignore`).
