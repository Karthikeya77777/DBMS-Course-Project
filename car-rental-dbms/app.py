"""Car Rental Reservation and Vehicle Return Management System (Flask + MySQL)."""
import math
import os
import re
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

import mysql.connector
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from markupsafe import Markup

from db import query_all, query_one, transaction

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-me")

VEHICLE_TYPES = ["Hatchback", "Sedan", "SUV", "MUV", "Convertible", "Van"]
FUEL_TYPES = ["Petrol", "Diesel", "Electric", "CNG", "Hybrid"]
TRANSMISSIONS = ["Manual", "Automatic"]
EDITABLE_STATUSES = ["Available", "Maintenance"]  # 'Rented' is set only by the rental process
CONDITIONS = ["Excellent", "Good", "Fair", "Damaged"]
RES_STATUSES = ["Confirmed", "Active", "Completed", "Cancelled"]


class BusinessError(Exception):
    """A rule of the rental business was broken (shown to the user as a message)."""


# ---------------------------------------------------------------- security / template helpers
@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get("csrf_token")
        if not token or token != request.form.get("csrf_token"):
            abort(400, "Invalid or missing security token. Reload the page and try again.")


def csrf_field():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return Markup('<input type="hidden" name="csrf_token" value="%s">' % session["csrf_token"])


app.jinja_env.globals["csrf_field"] = csrf_field
app.jinja_env.globals.update(
    VEHICLE_TYPES=VEHICLE_TYPES, FUEL_TYPES=FUEL_TYPES, TRANSMISSIONS=TRANSMISSIONS,
    EDITABLE_STATUSES=EDITABLE_STATUSES, CONDITIONS=CONDITIONS, RES_STATUSES=RES_STATUSES)


@app.template_filter("money")
def money(value):
    return "₹{:,.2f}".format(value if value is not None else 0)


@app.template_filter("dt")
def fmt_dt(value):
    return value.strftime("%d %b %Y, %H:%M") if value else "-"


@app.template_filter("d")
def fmt_d(value):
    return value.strftime("%d %b %Y") if value else "-"


@app.errorhandler(mysql.connector.Error)
def handle_db_error(err):
    app.logger.exception("Database error")
    return render_template("error.html", title="Database error",
                           message="The database could not complete the request. "
                                   "Check that MySQL is running and the .env credentials are correct."), 500


@app.errorhandler(400)
@app.errorhandler(404)
def handle_http_error(err):
    return render_template("error.html", title=err.name, message=err.description), err.code


# ---------------------------------------------------------------- generic helpers
def get_settings():
    rows = query_all("SELECT setting_key, setting_value FROM settings")
    return {r["setting_key"]: r["setting_value"] for r in rows}


def parse_date(text):
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(text):
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def parse_int(text, label, errors, minimum=0, maximum=10_000_000):
    try:
        value = int((text or "").strip())
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return None
    if value < minimum or value > maximum:
        errors.append(f"{label} must be between {minimum} and {maximum}.")
        return None
    return value


def parse_money(text, label, errors, maximum, allow_zero=True):
    text = (text or "").strip()
    if text == "":
        text = "0"
    try:
        value = Decimal(text)
    except InvalidOperation:
        errors.append(f"{label} must be a number.")
        return Decimal("0.00")
    if not value.is_finite() or value != value.quantize(Decimal("0.01")):
        errors.append(f"{label} must have at most 2 decimal places.")
        return Decimal("0.00")
    if value < 0 or (value == 0 and not allow_zero) or value > maximum:
        errors.append(f"{label} must be between {'0' if allow_zero else '0.01'} and {maximum}.")
        return Decimal("0.00")
    return value.quantize(Decimal("0.01"))


def duplicate_message(err):
    """Turn a MySQL duplicate-key error into a friendly sentence."""
    text = str(err)
    for key, label in (("phone", "phone number"), ("email", "email address"),
                       ("license", "driving licence number"), ("registration", "registration number")):
        if key in text:
            return f"That {label} is already registered."
    return "A record with the same unique value already exists."


# ---------------------------------------------------------------- dashboard
@app.route("/")
def dashboard():
    stats = query_one("""
        SELECT (SELECT COUNT(*) FROM vehicles) AS total_vehicles,
               (SELECT COUNT(*) FROM vehicles WHERE availability_status='Available') AS available_vehicles,
               (SELECT COUNT(*) FROM vehicles WHERE availability_status='Rented') AS rented_vehicles,
               (SELECT COUNT(*) FROM vehicles WHERE availability_status='Maintenance') AS maintenance_vehicles,
               (SELECT COUNT(*) FROM customers) AS total_customers,
               (SELECT COUNT(*) FROM reservations) AS total_reservations,
               (SELECT COUNT(*) FROM rentals WHERE rental_status='Active') AS active_rentals,
               (SELECT COUNT(*) FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
                 WHERE rt.rental_status='Active' AND r.expected_return_date < CURDATE()) AS overdue_rentals,
               (SELECT COALESCE(SUM(final_amount),0) FROM rentals WHERE rental_status='Returned') AS revenue""")
    recent_reservations = query_all("""
        SELECT r.reservation_id, r.start_date, r.expected_return_date, r.reservation_status,
               c.full_name, v.brand, v.model, v.registration_number
        FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
        JOIN vehicles v ON v.vehicle_id=r.vehicle_id ORDER BY r.reservation_id DESC LIMIT 5""")
    recent_returns = query_all("""
        SELECT rt.rental_id, rt.actual_return_datetime, rt.final_amount, c.full_name, v.brand, v.model
        FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
        JOIN customers c ON c.customer_id=r.customer_id JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        WHERE rt.rental_status='Returned' ORDER BY rt.actual_return_datetime DESC LIMIT 5""")
    return render_template("dashboard.html", s=stats, recent_reservations=recent_reservations,
                           recent_returns=recent_returns)


# ---------------------------------------------------------------- vehicles
def validate_vehicle(f):
    errors = []
    reg = f.get("registration_number", "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9 -]{5,20}", reg):
        errors.append("Registration number must be 5-20 letters, digits, spaces or hyphens.")
    brand, model = f.get("brand", "").strip(), f.get("model", "").strip()
    if not brand or len(brand) > 50:
        errors.append("Brand is required (max 50 characters).")
    if not model or len(model) > 50:
        errors.append("Model is required (max 50 characters).")
    if f.get("vehicle_type") not in VEHICLE_TYPES:
        errors.append("Choose a valid vehicle type.")
    if f.get("fuel_type") not in FUEL_TYPES:
        errors.append("Choose a valid fuel type.")
    if f.get("transmission_type") not in TRANSMISSIONS:
        errors.append("Choose a valid transmission type.")
    year = parse_int(f.get("manufacturing_year"), "Manufacturing year", errors, 1990, date.today().year + 1)
    seats = parse_int(f.get("seating_capacity"), "Seating capacity", errors, 1, 20)
    rent = parse_money(f.get("daily_rent"), "Daily rent", errors, Decimal("100000"), allow_zero=False)
    status = f.get("availability_status", "Available")
    clean = dict(registration_number=reg, brand=brand, model=model, vehicle_type=f.get("vehicle_type"),
                 manufacturing_year=year, fuel_type=f.get("fuel_type"),
                 transmission_type=f.get("transmission_type"), seating_capacity=seats,
                 daily_rent=rent, availability_status=status)
    return clean, errors


@app.route("/vehicles")
def vehicles():
    q, vtype, status = request.args.get("q", "").strip(), request.args.get("type", ""), request.args.get("status", "")
    sql, params = "SELECT * FROM vehicles WHERE 1=1", []
    if q:
        sql += " AND (registration_number LIKE %s OR brand LIKE %s OR model LIKE %s)"
        params += [f"%{q}%"] * 3
    if vtype:
        sql += " AND vehicle_type = %s"
        params.append(vtype)
    if status:
        sql += " AND availability_status = %s"
        params.append(status)
    rows = query_all(sql + " ORDER BY vehicle_id", params)
    return render_template("vehicles.html", vehicles=rows, q=q, vtype=vtype, status=status)


@app.route("/vehicles/add", methods=["GET", "POST"])
def vehicle_add():
    form = request.form if request.method == "POST" else {"availability_status": "Available"}
    if request.method == "POST":
        clean, errors = validate_vehicle(request.form)
        if clean["availability_status"] not in EDITABLE_STATUSES:
            errors.append("A new vehicle can only be Available or in Maintenance.")
        if not errors:
            try:
                with transaction() as cur:
                    cur.execute("""INSERT INTO vehicles (registration_number, brand, model, vehicle_type,
                        manufacturing_year, fuel_type, transmission_type, seating_capacity, daily_rent,
                        availability_status) VALUES (%(registration_number)s, %(brand)s, %(model)s,
                        %(vehicle_type)s, %(manufacturing_year)s, %(fuel_type)s, %(transmission_type)s,
                        %(seating_capacity)s, %(daily_rent)s, %(availability_status)s)""", clean)
                    new_id = cur.lastrowid
                flash("Vehicle added successfully.", "success")
                return redirect(url_for("vehicle_detail", vehicle_id=new_id))
            except mysql.connector.IntegrityError as err:
                errors.append(duplicate_message(err))
        for e in errors:
            flash(e, "danger")
    return render_template("vehicle_form.html", form=form, editing=False, locked=False)


@app.route("/vehicles/<int:vehicle_id>")
def vehicle_detail(vehicle_id):
    vehicle = query_one("SELECT * FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
    if not vehicle:
        abort(404, "Vehicle not found.")
    history = query_all("""
        SELECT r.reservation_id, r.start_date, r.expected_return_date, r.reservation_status,
               r.total_estimated_cost, c.full_name, rt.rental_id, rt.final_amount, rt.rental_status
        FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
        LEFT JOIN rentals rt ON rt.reservation_id=r.reservation_id
        WHERE r.vehicle_id=%s ORDER BY r.start_date DESC""", (vehicle_id,))
    return render_template("vehicle_detail.html", v=vehicle, history=history)


@app.route("/vehicles/<int:vehicle_id>/edit", methods=["GET", "POST"])
def vehicle_edit(vehicle_id):
    vehicle = query_one("SELECT * FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
    if not vehicle:
        abort(404, "Vehicle not found.")
    locked = vehicle["availability_status"] == "Rented"  # status cannot be changed while rented out
    form = request.form if request.method == "POST" else vehicle
    if request.method == "POST":
        clean, errors = validate_vehicle(request.form)
        if locked:
            clean["availability_status"] = "Rented"
        elif clean["availability_status"] not in EDITABLE_STATUSES:
            errors.append("Status must be Available or Maintenance.")
        if not errors:
            clean["vehicle_id"] = vehicle_id
            try:
                with transaction() as cur:
                    cur.execute("""UPDATE vehicles SET registration_number=%(registration_number)s, brand=%(brand)s,
                        model=%(model)s, vehicle_type=%(vehicle_type)s, manufacturing_year=%(manufacturing_year)s,
                        fuel_type=%(fuel_type)s, transmission_type=%(transmission_type)s,
                        seating_capacity=%(seating_capacity)s, daily_rent=%(daily_rent)s,
                        availability_status=%(availability_status)s WHERE vehicle_id=%(vehicle_id)s""", clean)
                flash("Vehicle updated successfully.", "success")
                return redirect(url_for("vehicle_detail", vehicle_id=vehicle_id))
            except mysql.connector.IntegrityError as err:
                errors.append(duplicate_message(err))
        for e in errors:
            flash(e, "danger")
    return render_template("vehicle_form.html", form=form, editing=True, locked=locked, vehicle_id=vehicle_id)


@app.route("/vehicles/<int:vehicle_id>/delete", methods=["POST"])
def vehicle_delete(vehicle_id):
    used = query_one("SELECT COUNT(*) AS n FROM reservations WHERE vehicle_id=%s", (vehicle_id,))["n"]
    if used:
        flash(f"Cannot delete: this vehicle has {used} reservation record(s). History is preserved. "
              "Set it to Maintenance instead.", "danger")
        return redirect(url_for("vehicle_detail", vehicle_id=vehicle_id))
    try:
        with transaction() as cur:
            cur.execute("DELETE FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
        flash("Vehicle deleted.", "success")
    except mysql.connector.IntegrityError:
        flash("Cannot delete: the vehicle is referenced by other records.", "danger")
        return redirect(url_for("vehicle_detail", vehicle_id=vehicle_id))
    return redirect(url_for("vehicles"))


# ---------------------------------------------------------------- customers
def validate_customer(f):
    errors = []
    name = f.get("full_name", "").strip()
    phone = f.get("phone", "").strip()
    email = f.get("email", "").strip().lower()
    lic = f.get("driving_license_number", "").strip().upper()
    address = f.get("address", "").strip()
    if len(name) < 2 or len(name) > 100:
        errors.append("Full name must be 2-100 characters.")
    if not re.fullmatch(r"\+?[0-9]{10,14}", phone):
        errors.append("Phone must be 10-14 digits (optional leading +).")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 120:
        errors.append("Enter a valid email address.")
    if not re.fullmatch(r"[A-Z0-9 -]{8,30}", lic):
        errors.append("Driving licence number must be 8-30 letters, digits, spaces or hyphens.")
    if not address or len(address) > 255:
        errors.append("Address is required (max 255 characters).")
    return dict(full_name=name, phone=phone, email=email, driving_license_number=lic, address=address), errors


@app.route("/customers")
def customers():
    q = request.args.get("q", "").strip()
    sql, params = "SELECT * FROM customers WHERE 1=1", []
    if q:
        sql += " AND (full_name LIKE %s OR phone LIKE %s OR email LIKE %s OR driving_license_number LIKE %s)"
        params = [f"%{q}%"] * 4
    return render_template("customers.html", customers=query_all(sql + " ORDER BY customer_id", params), q=q)


@app.route("/customers/add", methods=["GET", "POST"])
def customer_add():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        clean, errors = validate_customer(request.form)
        if not errors:
            try:
                with transaction() as cur:
                    cur.execute("""INSERT INTO customers (full_name, phone, email, driving_license_number, address)
                        VALUES (%(full_name)s, %(phone)s, %(email)s, %(driving_license_number)s, %(address)s)""", clean)
                    new_id = cur.lastrowid
                flash("Customer added successfully.", "success")
                return redirect(url_for("customer_detail", customer_id=new_id))
            except mysql.connector.IntegrityError as err:
                errors.append(duplicate_message(err))
        for e in errors:
            flash(e, "danger")
    return render_template("customer_form.html", form=form, editing=False)


@app.route("/customers/<int:customer_id>")
def customer_detail(customer_id):
    customer = query_one("SELECT * FROM customers WHERE customer_id=%s", (customer_id,))
    if not customer:
        abort(404, "Customer not found.")
    history = query_all("""
        SELECT r.reservation_id, r.start_date, r.expected_return_date, r.reservation_status,
               v.brand, v.model, v.registration_number, rt.rental_id, rt.final_amount
        FROM reservations r JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        LEFT JOIN rentals rt ON rt.reservation_id=r.reservation_id
        WHERE r.customer_id=%s ORDER BY r.start_date DESC""", (customer_id,))
    return render_template("customer_detail.html", c=customer, history=history)


@app.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
def customer_edit(customer_id):
    customer = query_one("SELECT * FROM customers WHERE customer_id=%s", (customer_id,))
    if not customer:
        abort(404, "Customer not found.")
    form = request.form if request.method == "POST" else customer
    if request.method == "POST":
        clean, errors = validate_customer(request.form)
        if not errors:
            clean["customer_id"] = customer_id
            try:
                with transaction() as cur:
                    cur.execute("""UPDATE customers SET full_name=%(full_name)s, phone=%(phone)s, email=%(email)s,
                        driving_license_number=%(driving_license_number)s, address=%(address)s
                        WHERE customer_id=%(customer_id)s""", clean)
                flash("Customer updated successfully.", "success")
                return redirect(url_for("customer_detail", customer_id=customer_id))
            except mysql.connector.IntegrityError as err:
                errors.append(duplicate_message(err))
        for e in errors:
            flash(e, "danger")
    return render_template("customer_form.html", form=form, editing=True, customer_id=customer_id)


@app.route("/customers/<int:customer_id>/delete", methods=["POST"])
def customer_delete(customer_id):
    used = query_one("SELECT COUNT(*) AS n FROM reservations WHERE customer_id=%s", (customer_id,))["n"]
    if used:
        flash(f"Cannot delete: this customer has {used} reservation record(s). History is preserved.", "danger")
        return redirect(url_for("customer_detail", customer_id=customer_id))
    with transaction() as cur:
        cur.execute("DELETE FROM customers WHERE customer_id=%s", (customer_id,))
    flash("Customer deleted.", "success")
    return redirect(url_for("customers"))


# ---------------------------------------------------------------- reservations
def save_reservation(f, reservation_id=None, original_start=None):
    """Validate and save a reservation. Raises BusinessError with a user-friendly message."""
    errors = []
    customer_id = parse_int(f.get("customer_id"), "Customer", errors, 1)
    vehicle_id = parse_int(f.get("vehicle_id"), "Vehicle", errors, 1)
    start, end = parse_date(f.get("start_date")), parse_date(f.get("expected_return_date"))
    if not start or not end:
        errors.append("Enter valid start and return dates.")
    else:
        if end <= start:
            errors.append("Return date must be after the start date.")
        if start < date.today() and start != original_start:
            errors.append("Start date cannot be in the past.")
    if errors:
        raise BusinessError(" ".join(errors))
    with transaction() as cur:
        # Lock the vehicle row so two people cannot book overlapping dates at the same moment.
        cur.execute("SELECT * FROM vehicles WHERE vehicle_id=%s FOR UPDATE", (vehicle_id,))
        vehicle = cur.fetchone()
        cur.execute("SELECT customer_id FROM customers WHERE customer_id=%s", (customer_id,))
        if not vehicle or not cur.fetchone():
            raise BusinessError("Selected customer or vehicle does not exist.")
        if vehicle["availability_status"] == "Maintenance":
            raise BusinessError("This vehicle is under maintenance and cannot be reserved.")
        cur.execute("""SELECT reservation_id, start_date, expected_return_date FROM reservations
            WHERE vehicle_id=%s AND reservation_status IN ('Confirmed','Active')
              AND start_date < %s AND expected_return_date > %s AND reservation_id <> %s""",
                    (vehicle_id, end, start, reservation_id or 0))
        clash = cur.fetchone()
        if clash:
            raise BusinessError(f"Vehicle already reserved from {clash['start_date']:%d %b} to "
                                f"{clash['expected_return_date']:%d %b} (reservation #{clash['reservation_id']}).")
        cost = vehicle["daily_rent"] * (end - start).days
        if reservation_id:
            cur.execute("""UPDATE reservations SET customer_id=%s, vehicle_id=%s, start_date=%s,
                expected_return_date=%s, total_estimated_cost=%s WHERE reservation_id=%s""",
                        (customer_id, vehicle_id, start, end, cost, reservation_id))
            return reservation_id
        cur.execute("""INSERT INTO reservations (customer_id, vehicle_id, booking_date, start_date,
            expected_return_date, reservation_status, total_estimated_cost)
            VALUES (%s, %s, CURDATE(), %s, %s, 'Confirmed', %s)""", (customer_id, vehicle_id, start, end, cost))
        return cur.lastrowid


def reservation_form_data():
    return dict(customers=query_all("SELECT customer_id, full_name, phone FROM customers ORDER BY full_name"),
                vehicles=query_all("""SELECT vehicle_id, brand, model, registration_number, daily_rent
                    FROM vehicles WHERE availability_status <> 'Maintenance' ORDER BY brand, model"""))


@app.route("/reservations")
def reservations():
    q, vq = request.args.get("q", "").strip(), request.args.get("vehicle", "").strip()
    status = request.args.get("status", "")
    dfrom, dto = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
    sql = """SELECT r.*, c.full_name, v.brand, v.model, v.registration_number
             FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
             JOIN vehicles v ON v.vehicle_id=r.vehicle_id WHERE 1=1"""
    params = []
    if q:
        sql += " AND (c.full_name LIKE %s OR c.phone LIKE %s)"
        params += [f"%{q}%"] * 2
    if vq:
        sql += " AND (v.registration_number LIKE %s OR v.brand LIKE %s OR v.model LIKE %s)"
        params += [f"%{vq}%"] * 3
    if status:
        sql += " AND r.reservation_status=%s"
        params.append(status)
    if dfrom:
        sql += " AND r.expected_return_date >= %s"
        params.append(dfrom)
    if dto:
        sql += " AND r.start_date <= %s"
        params.append(dto)
    rows = query_all(sql + " ORDER BY r.reservation_id DESC", params)
    return render_template("reservations.html", reservations=rows, q=q, vq=vq, status=status,
                           dfrom=request.args.get("from", ""), dto=request.args.get("to", ""))


@app.route("/reservations/new", methods=["GET", "POST"])
def reservation_new():
    form = request.form if request.method == "POST" else {
        "customer_id": request.args.get("customer_id", ""), "vehicle_id": request.args.get("vehicle_id", "")}
    if request.method == "POST":
        try:
            new_id = save_reservation(request.form)
            flash("Reservation created successfully.", "success")
            return redirect(url_for("reservation_detail", reservation_id=new_id))
        except BusinessError as err:
            flash(str(err), "danger")
    return render_template("reservation_form.html", form=form, editing=False, today=date.today(),
                           **reservation_form_data())


@app.route("/reservations/<int:reservation_id>")
def reservation_detail(reservation_id):
    r = query_one("""SELECT r.*, c.full_name, c.phone, v.brand, v.model, v.registration_number, v.daily_rent,
                            rt.rental_id, rt.rental_status
        FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
        JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        LEFT JOIN rentals rt ON rt.reservation_id=r.reservation_id
        WHERE r.reservation_id=%s""", (reservation_id,))
    if not r:
        abort(404, "Reservation not found.")
    return render_template("reservation_detail.html", r=r, days=(r["expected_return_date"] - r["start_date"]).days)


@app.route("/reservations/<int:reservation_id>/edit", methods=["GET", "POST"])
def reservation_edit(reservation_id):
    r = query_one("SELECT * FROM reservations WHERE reservation_id=%s", (reservation_id,))
    if not r:
        abort(404, "Reservation not found.")
    if r["reservation_status"] != "Confirmed":
        flash("Only Confirmed reservations can be edited.", "warning")
        return redirect(url_for("reservation_detail", reservation_id=reservation_id))
    form = request.form if request.method == "POST" else r
    if request.method == "POST":
        try:
            save_reservation(request.form, reservation_id, r["start_date"])
            flash("Reservation updated successfully.", "success")
            return redirect(url_for("reservation_detail", reservation_id=reservation_id))
        except BusinessError as err:
            flash(str(err), "danger")
    return render_template("reservation_form.html", form=form, editing=True, today=date.today(),
                           reservation_id=reservation_id, **reservation_form_data())


@app.route("/reservations/<int:reservation_id>/cancel", methods=["POST"])
def reservation_cancel(reservation_id):
    with transaction() as cur:
        cur.execute("SELECT reservation_status FROM reservations WHERE reservation_id=%s FOR UPDATE", (reservation_id,))
        row = cur.fetchone()
        if not row:
            abort(404, "Reservation not found.")
        if row["reservation_status"] != "Confirmed":
            flash("Only Confirmed reservations can be cancelled.", "danger")
        else:
            cur.execute("UPDATE reservations SET reservation_status='Cancelled' WHERE reservation_id=%s", (reservation_id,))
            flash("Reservation cancelled. The record is kept in history.", "success")
    return redirect(url_for("reservation_detail", reservation_id=reservation_id))


# ---------------------------------------------------------------- rentals (pickup)
ACTIVE_RENTAL_SQL = """
    SELECT rt.*, r.start_date, r.expected_return_date, r.vehicle_id, c.full_name, c.phone,
           v.brand, v.model, v.registration_number, v.daily_rent,
           (r.expected_return_date < CURDATE()) AS is_overdue,
           GREATEST(DATEDIFF(CURDATE(), r.expected_return_date), 0) AS days_overdue
    FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
    JOIN customers c ON c.customer_id=r.customer_id JOIN vehicles v ON v.vehicle_id=r.vehicle_id
    WHERE rt.rental_status='Active'"""


@app.route("/rentals")
def rentals():
    rows = query_all(ACTIVE_RENTAL_SQL + " ORDER BY is_overdue DESC, r.expected_return_date")
    return render_template("rentals.html", rentals=rows)


def pickup_candidates():
    return query_all("""
        SELECT r.reservation_id, r.start_date, r.expected_return_date, c.full_name, v.brand, v.model,
               v.registration_number, v.availability_status,
               COALESCE((SELECT MAX(rt2.return_odometer) FROM rentals rt2
                         JOIN reservations r2 ON r2.reservation_id=rt2.reservation_id
                         WHERE r2.vehicle_id=r.vehicle_id), 0) AS last_odometer
        FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
        JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        WHERE r.reservation_status='Confirmed' AND r.start_date <= CURDATE() AND r.expected_return_date >= CURDATE()
        ORDER BY r.start_date""")


@app.route("/rentals/start", methods=["GET", "POST"])
def rental_start():
    form = request.form if request.method == "POST" else {
        "reservation_id": request.args.get("reservation_id", ""), "pickup_datetime": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "pickup_condition": "Good"}
    if request.method == "POST":
        try:
            rental_id = start_rental(request.form)
            flash("Rental started. The vehicle is now marked Rented.", "success")
            return redirect(url_for("rentals"))
        except BusinessError as err:
            flash(str(err), "danger")
        except mysql.connector.Error as err:
            flash("Could not start the rental: " + (err.msg or "database error"), "danger")
    return render_template("rental_start.html", form=form, candidates=pickup_candidates())


def start_rental(f):
    errors = []
    reservation_id = parse_int(f.get("reservation_id"), "Reservation", errors, 1)
    pickup = parse_datetime(f.get("pickup_datetime"))
    odometer = parse_int(f.get("pickup_odometer"), "Pickup odometer", errors, 0, 2_000_000)
    condition = f.get("pickup_condition")
    if not pickup:
        errors.append("Enter a valid pickup date and time.")
    elif pickup > datetime.now() + timedelta(minutes=5):
        errors.append("Pickup time cannot be in the future.")
    if condition not in CONDITIONS:
        errors.append("Choose the vehicle condition at pickup.")
    if errors:
        raise BusinessError(" ".join(errors))
    with transaction() as cur:
        cur.execute("SELECT * FROM reservations WHERE reservation_id=%s FOR UPDATE", (reservation_id,))
        res = cur.fetchone()
        if not res:
            raise BusinessError("Reservation not found.")
        cur.execute("SELECT * FROM vehicles WHERE vehicle_id=%s FOR UPDATE", (res["vehicle_id"],))
        vehicle = cur.fetchone()
        if res["reservation_status"] != "Confirmed":
            raise BusinessError("Only Confirmed reservations can be picked up.")
        if pickup.date() < res["start_date"] or pickup.date() > res["expected_return_date"]:
            raise BusinessError("Pickup must be between the reservation start and expected return dates.")
        if vehicle["availability_status"] != "Available":
            raise BusinessError(f"Vehicle is currently {vehicle['availability_status']} and cannot be issued.")
        cur.execute("""SELECT COUNT(*) AS n FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
            WHERE r.vehicle_id=%s AND rt.rental_status='Active'""", (res["vehicle_id"],))
        if cur.fetchone()["n"]:
            raise BusinessError("This vehicle already has an active rental.")
        cur.execute("""SELECT COALESCE(MAX(rt.return_odometer),0) AS last FROM rentals rt
            JOIN reservations r ON r.reservation_id=rt.reservation_id WHERE r.vehicle_id=%s""", (res["vehicle_id"],))
        last = cur.fetchone()["last"]
        if odometer < last:
            raise BusinessError(f"Pickup odometer cannot be below the last recorded reading ({last} km).")
        cur.execute("""INSERT INTO rentals (reservation_id, actual_pickup_datetime, pickup_odometer,
            pickup_condition, rental_status) VALUES (%s, %s, %s, %s, 'Active')""",
                    (reservation_id, pickup, odometer, condition))
        rental_id = cur.lastrowid
        cur.execute("UPDATE reservations SET reservation_status='Active' WHERE reservation_id=%s", (reservation_id,))
        cur.execute("UPDATE vehicles SET availability_status='Rented' WHERE vehicle_id=%s", (res["vehicle_id"],))
        return rental_id


# ---------------------------------------------------------------- returns and billing
def calculate_bill(daily_rent, pickup, returned, expected_date, settings, fuel, damage, other):
    """Billing policy (documented in README):
    * Rent = daily_rent x calendar days between pickup date and return date (minimum 1 day).
    * Return is on time until 23:59 of the expected return date + grace hours.
    * Each late day (or part of a day) adds daily_rent x late_fee_percent% as a late fee.
    """
    grace = float(settings["late_grace_hours"])
    percent = settings["late_fee_percent"]
    days = max(1, (returned.date() - pickup.date()).days)
    deadline = datetime.combine(expected_date + timedelta(days=1), time.min) + timedelta(hours=grace)
    late_hours = max(0.0, (returned - deadline).total_seconds() / 3600)
    late_days = math.ceil(late_hours / 24) if late_hours > 0 else 0
    if late_days == 0:  # on time: never bill more than the booked days
        days = min(days, max(1, (expected_date - pickup.date()).days))
    rental_charge = daily_rent * days
    late_fee = (daily_rent * late_days * percent / Decimal(100)).quantize(Decimal("0.01"))
    extras = fuel + damage + other
    return dict(days=days, late_days=late_days, late_hours=round(late_hours, 1), rental_charge=rental_charge,
                late_fee=late_fee, fuel=fuel, damage=damage, other=other, extras=extras,
                total=rental_charge + late_fee + extras, grace=grace, percent=percent)


def read_return_form(f, rental, settings):
    """Validate the return form; returns (values, bill, errors)."""
    errors = []
    returned = parse_datetime(f.get("return_datetime"))
    odometer = parse_int(f.get("return_odometer"), "Return odometer", errors, 0, 2_000_000)
    condition = f.get("return_condition")
    cap = settings["max_extra_charge"]
    fuel = parse_money(f.get("fuel_charge"), "Fuel charge", errors, cap)
    damage = parse_money(f.get("damage_charge"), "Damage charge", errors, cap)
    other = parse_money(f.get("other_charge"), "Other charge", errors, cap)
    if not returned:
        errors.append("Enter a valid return date and time.")
    elif returned < rental["actual_pickup_datetime"]:
        errors.append("Return time cannot be before the pickup time.")
    elif returned > datetime.now() + timedelta(minutes=5):
        errors.append("Return time cannot be in the future.")
    if odometer is not None and odometer < rental["pickup_odometer"]:
        errors.append(f"Return odometer cannot be below the pickup reading ({rental['pickup_odometer']} km).")
    if condition not in CONDITIONS:
        errors.append("Choose the vehicle condition at return.")
    if condition == "Damaged" and damage == 0:
        errors.append("Vehicle is marked Damaged: enter the damage charge (or choose another condition).")
    bill = None
    if not errors:
        bill = calculate_bill(rental["daily_rent"], rental["actual_pickup_datetime"], returned,
                              rental["expected_return_date"], settings, fuel, damage, other)
    return dict(returned=returned, odometer=odometer, condition=condition), bill, errors


@app.route("/returns/new", methods=["GET", "POST"])
def return_new():
    settings = get_settings()
    active = query_all(ACTIVE_RENTAL_SQL + " ORDER BY rt.rental_id")
    form = request.form if request.method == "POST" else {
        "rental_id": request.args.get("rental_id", ""), "return_datetime": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "return_condition": "Good"}
    bill, selected = None, None
    rental_id = parse_int(form.get("rental_id"), "Rental", [], 1)
    selected = next((r for r in active if r["rental_id"] == rental_id), None)
    if request.method == "POST":
        if not selected:
            flash("Choose an active rental to return.", "danger")
        else:
            values, bill, errors = read_return_form(request.form, selected, settings)
            for e in errors:
                flash(e, "danger")
            if bill and request.form.get("action") == "complete":
                try:
                    complete_return(selected["rental_id"], values, bill)
                    flash("Return completed and saved.", "success")
                    return redirect(url_for("invoice", rental_id=selected["rental_id"]))
                except BusinessError as err:
                    flash(str(err), "danger")
                    bill = None
            elif bill:
                flash("Bill calculated. Review it below, then click Complete return.", "info")
    return render_template("return_form.html", form=form, active=active, selected=selected, bill=bill,
                           settings=settings)


def complete_return(rental_id, values, bill):
    with transaction() as cur:
        cur.execute("""SELECT rt.*, r.vehicle_id, r.reservation_id AS res_id FROM rentals rt
            JOIN reservations r ON r.reservation_id=rt.reservation_id WHERE rt.rental_id=%s FOR UPDATE""", (rental_id,))
        rental = cur.fetchone()
        if not rental:
            raise BusinessError("Rental not found.")
        if rental["rental_status"] != "Active":  # blocks double returns
            raise BusinessError("This rental has already been returned.")
        cur.execute("""UPDATE rentals SET actual_return_datetime=%s, return_odometer=%s, return_condition=%s,
            rental_charge=%s, fuel_charge=%s, damage_charge=%s, other_charge=%s, late_fee=%s, final_amount=%s,
            rental_status='Returned' WHERE rental_id=%s""",
                    (values["returned"], values["odometer"], values["condition"], bill["rental_charge"],
                     bill["fuel"], bill["damage"], bill["other"], bill["late_fee"], bill["total"], rental_id))
        cur.execute("UPDATE reservations SET reservation_status='Completed' WHERE reservation_id=%s", (rental["res_id"],))
        new_status = "Maintenance" if values["condition"] == "Damaged" else "Available"
        cur.execute("UPDATE vehicles SET availability_status=%s WHERE vehicle_id=%s", (new_status, rental["vehicle_id"]))


@app.route("/returns")
def returns():
    q = request.args.get("q", "").strip()
    dfrom, dto = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
    sql = """SELECT rt.*, r.expected_return_date, c.full_name, v.brand, v.model, v.registration_number
        FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
        JOIN customers c ON c.customer_id=r.customer_id JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        WHERE rt.rental_status='Returned'"""
    params = []
    if q:
        sql += " AND (c.full_name LIKE %s OR v.registration_number LIKE %s OR v.model LIKE %s)"
        params += [f"%{q}%"] * 3
    if dfrom:
        sql += " AND DATE(rt.actual_return_datetime) >= %s"
        params.append(dfrom)
    if dto:
        sql += " AND DATE(rt.actual_return_datetime) <= %s"
        params.append(dto)
    rows = query_all(sql + " ORDER BY rt.actual_return_datetime DESC", params)
    return render_template("returns.html", rows=rows, q=q, dfrom=request.args.get("from", ""),
                           dto=request.args.get("to", ""))


@app.route("/returns/<int:rental_id>/invoice")
def invoice(rental_id):
    r = query_one("""SELECT rt.*, r.reservation_id, r.start_date, r.expected_return_date, r.total_estimated_cost,
            c.full_name, c.phone, c.email, c.driving_license_number, v.brand, v.model, v.registration_number,
            v.daily_rent FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
        JOIN customers c ON c.customer_id=r.customer_id JOIN vehicles v ON v.vehicle_id=r.vehicle_id
        WHERE rt.rental_id=%s""", (rental_id,))
    if not r:
        abort(404, "Rental not found.")
    if r["rental_status"] != "Returned":
        flash("This rental has not been returned yet.", "warning")
        return redirect(url_for("rentals"))
    days = max(1, round(float(r["rental_charge"] / r["daily_rent"])))
    return render_template("invoice.html", r=r, days=days, distance=r["return_odometer"] - r["pickup_odometer"])


# ---------------------------------------------------------------- reports
def build_report(name, args):
    dfrom, dto = parse_date(args.get("from")), parse_date(args.get("to"))
    today = date.today()
    money_cols = set()
    if name == "reservations":
        sql = """SELECT r.reservation_id, c.full_name, CONCAT(v.brand,' ',v.model) AS vehicle, r.start_date,
                 r.expected_return_date, r.reservation_status, r.total_estimated_cost
                 FROM reservations r JOIN customers c ON c.customer_id=r.customer_id
                 JOIN vehicles v ON v.vehicle_id=r.vehicle_id WHERE 1=1"""
        params = []
        if dfrom:
            sql += " AND r.expected_return_date >= %s"; params.append(dfrom)
        if dto:
            sql += " AND r.start_date <= %s"; params.append(dto)
        sql += " ORDER BY r.start_date DESC"
        cols = [("reservation_id", "Res #"), ("full_name", "Customer"), ("vehicle", "Vehicle"), ("start_date", "Start"),
                ("expected_return_date", "Expected return"), ("reservation_status", "Status"),
                ("total_estimated_cost", "Estimated cost")]
        money_cols, title = {"total_estimated_cost"}, "All reservations"
    elif name == "active":
        sql, params = ACTIVE_RENTAL_SQL + " ORDER BY r.expected_return_date", []
        cols = [("rental_id", "Rental #"), ("full_name", "Customer"), ("registration_number", "Vehicle reg."),
                ("actual_pickup_datetime", "Picked up"), ("expected_return_date", "Expected return"),
                ("days_overdue", "Days overdue")]
        title = "Active rentals"
    elif name == "available":
        start = dfrom or today
        end = dto or (start + timedelta(days=1))
        sql = """SELECT v.vehicle_id, v.registration_number, v.brand, v.model, v.vehicle_type, v.daily_rent
                 FROM vehicles v WHERE v.availability_status <> 'Maintenance'
                 AND NOT EXISTS (SELECT 1 FROM reservations r WHERE r.vehicle_id=v.vehicle_id
                     AND r.reservation_status IN ('Confirmed','Active')
                     AND r.start_date < %s AND r.expected_return_date > %s)
                 AND (v.availability_status='Available' OR %s > %s) ORDER BY v.brand, v.model"""
        params = [end, start, start, today]
        cols = [("vehicle_id", "ID"), ("registration_number", "Registration"), ("brand", "Brand"),
                ("model", "Model"), ("vehicle_type", "Type"), ("daily_rent", "Daily rent")]
        money_cols, title = {"daily_rent"}, f"Vehicles free from {start:%d %b %Y} to {end:%d %b %Y}"
    elif name == "returns":
        sql = """SELECT rt.rental_id, c.full_name, CONCAT(v.brand,' ',v.model) AS vehicle,
                 rt.actual_return_datetime, rt.late_fee, rt.final_amount
                 FROM rentals rt JOIN reservations r ON r.reservation_id=rt.reservation_id
                 JOIN customers c ON c.customer_id=r.customer_id JOIN vehicles v ON v.vehicle_id=r.vehicle_id
                 WHERE rt.rental_status='Returned'"""
        params = []
        if dfrom:
            sql += " AND DATE(rt.actual_return_datetime) >= %s"; params.append(dfrom)
        if dto:
            sql += " AND DATE(rt.actual_return_datetime) <= %s"; params.append(dto)
        sql += " ORDER BY rt.actual_return_datetime DESC"
        cols = [("rental_id", "Rental #"), ("full_name", "Customer"), ("vehicle", "Vehicle"),
                ("actual_return_datetime", "Returned"), ("late_fee", "Late fee"), ("final_amount", "Final amount")]
        money_cols, title = {"late_fee", "final_amount"}, "Completed vehicle returns"
    elif name == "overdue":
        sql, params = ACTIVE_RENTAL_SQL + " AND r.expected_return_date < CURDATE() ORDER BY days_overdue DESC", []
        cols = [("rental_id", "Rental #"), ("full_name", "Customer"), ("phone", "Phone"),
                ("registration_number", "Vehicle reg."), ("expected_return_date", "Expected return"),
                ("days_overdue", "Days overdue")]
        title = "Overdue vehicles"
    elif name == "revenue":
        sql = """SELECT LEFT(actual_return_datetime,7) AS month, COUNT(*) AS returns_count,
                 SUM(rental_charge) AS rent, SUM(fuel_charge+damage_charge+other_charge) AS extras,
                 SUM(late_fee) AS late_fees, SUM(final_amount) AS total
                 FROM rentals WHERE rental_status='Returned'"""
        params = []
        if dfrom:
            sql += " AND DATE(actual_return_datetime) >= %s"; params.append(dfrom)
        if dto:
            sql += " AND DATE(actual_return_datetime) <= %s"; params.append(dto)
        sql += " GROUP BY month ORDER BY month DESC"
        cols = [("month", "Month"), ("returns_count", "Returns"), ("rent", "Rent"), ("extras", "Extras"),
                ("late_fees", "Late fees"), ("total", "Total revenue")]
        money_cols, title = {"rent", "extras", "late_fees", "total"}, "Rental revenue by month"
    elif name == "utilization":
        start = dfrom or (today - timedelta(days=29))
        end = dto or today
        span = max(1, (end - start).days + 1)
        sql = """SELECT v.vehicle_id, CONCAT(v.brand,' ',v.model) AS vehicle, v.registration_number,
                 COUNT(rt.rental_id) AS rentals_count,
                 COALESCE(SUM(GREATEST(0, DATEDIFF(LEAST(DATE(COALESCE(rt.actual_return_datetime, NOW())), %s),
                     GREATEST(DATE(rt.actual_pickup_datetime), %s)) + 1)),0) AS days_rented,
                 ROUND(COALESCE(SUM(GREATEST(0, DATEDIFF(LEAST(DATE(COALESCE(rt.actual_return_datetime, NOW())), %s),
                     GREATEST(DATE(rt.actual_pickup_datetime), %s)) + 1)),0) * 100 / %s, 1) AS utilization_pct
                 FROM vehicles v LEFT JOIN reservations r ON r.vehicle_id=v.vehicle_id
                 LEFT JOIN rentals rt ON rt.reservation_id=r.reservation_id
                 GROUP BY v.vehicle_id, v.brand, v.model, v.registration_number ORDER BY utilization_pct DESC"""
        params = [end, start, end, start, span]
        cols = [("vehicle", "Vehicle"), ("registration_number", "Registration"), ("rentals_count", "Rentals"),
                ("days_rented", f"Days rented (of {span})"), ("utilization_pct", "Utilization %")]
        title = f"Vehicle utilization {start:%d %b} - {end:%d %b %Y}"
    elif name == "customer_history":
        sql = """SELECT c.full_name, r.reservation_id, CONCAT(v.brand,' ',v.model) AS vehicle, r.start_date,
                 r.expected_return_date, r.reservation_status, rt.final_amount
                 FROM customers c JOIN reservations r ON r.customer_id=c.customer_id
                 JOIN vehicles v ON v.vehicle_id=r.vehicle_id LEFT JOIN rentals rt ON rt.reservation_id=r.reservation_id
                 WHERE 1=1"""
        params = []
        cid = parse_int(args.get("customer_id", "0") or "0", "Customer", [], 0)
        if cid:
            sql += " AND c.customer_id=%s"; params.append(cid)
        sql += " ORDER BY c.full_name, r.start_date DESC"
        cols = [("full_name", "Customer"), ("reservation_id", "Res #"), ("vehicle", "Vehicle"), ("start_date", "Start"),
                ("expected_return_date", "Expected return"), ("reservation_status", "Status"),
                ("final_amount", "Amount billed")]
        money_cols, title = {"final_amount"}, "Customer rental history"
    else:
        abort(404, "Unknown report.")
    return title, cols, query_all(sql, params), money_cols


REPORT_LIST = [("reservations", "All reservations"), ("active", "Active rentals"), ("available", "Available vehicles"),
               ("returns", "Completed returns"), ("overdue", "Overdue vehicles"), ("revenue", "Rental revenue"),
               ("utilization", "Vehicle utilization"), ("customer_history", "Customer history")]


@app.route("/reports")
def reports():
    name = request.args.get("report", "revenue")
    title, cols, rows, money_cols = build_report(name, request.args)
    totals = query_one("""SELECT COALESCE(SUM(final_amount),0) AS revenue, COUNT(*) AS n FROM rentals
                          WHERE rental_status='Returned'""")
    customers_list = query_all("SELECT customer_id, full_name FROM customers ORDER BY full_name")
    return render_template("reports.html", name=name, title=title, cols=cols, rows=rows, money_cols=money_cols,
                           report_list=REPORT_LIST, dfrom=request.args.get("from", ""), dto=request.args.get("to", ""),
                           customers_list=customers_list, customer_id=request.args.get("customer_id", ""),
                           totals=totals)


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1")
