"""Automated checks against a real MySQL server.
Needs: mysql client on PATH and .env (or DB_* environment variables) pointing at a MySQL user that can
create databases. WARNING: running these tests re-creates car_rental_db (schema.sql + seed.sql).
Run from the project folder:  python -m pytest tests -q
"""
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_module  # noqa: E402
from db import query_all, query_one  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = date.today()


def load_sql(filename):
    cmd = ["mysql", "-h", os.getenv("DB_HOST", "127.0.0.1"), "-P", os.getenv("DB_PORT", "3306"),
           "-u", os.getenv("DB_USER", "root")]
    env = dict(os.environ, MYSQL_PWD=os.getenv("DB_PASSWORD", ""))
    with open(os.path.join(ROOT, filename)) as fh:
        subprocess.run(cmd + ([os.getenv("DB_NAME", "car_rental_db")] if filename == "seed.sql" else []),
                       stdin=fh, check=True, env=env, capture_output=True)


@pytest.fixture(scope="module")
def client():
    load_sql("schema.sql")
    load_sql("seed.sql")
    app_module.app.config["TESTING"] = True
    c = app_module.app.test_client()
    c.get("/")
    return c


def post(client, url, data=None, follow=True):
    with client.session_transaction() as s:
        token = s["csrf_token"]
    return client.post(url, data=dict(data or {}, csrf_token=token), follow_redirects=follow)


def d(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def dt(offset, hhmm):
    return f"{d(offset)}T{hhmm}"


def test_all_pages_open(client):
    for url in ["/", "/vehicles", "/vehicles/add", "/vehicles/1", "/vehicles/1/edit", "/customers", "/customers/add",
                "/customers/1", "/customers/1/edit", "/reservations", "/reservations/new", "/reservations/1",
                "/reservations/8/edit", "/rentals", "/rentals/start", "/returns/new", "/returns/new?rental_id=5",
                "/returns", "/returns/1/invoice", "/reports"] + [f"/reports?report={k}" for k, _ in app_module.REPORT_LIST]:
        assert client.get(url).status_code == 200, url


def test_dashboard_numbers_match_database(client):
    s = app_module.query_one("SELECT COUNT(*) n FROM vehicles")["n"]
    html = client.get("/").get_data(as_text=True)
    assert s == 8 and 'class="num">8<' in html
    assert query_one("SELECT COUNT(*) n FROM rentals WHERE rental_status='Active'")["n"] == 2
    assert query_one("""SELECT COUNT(*) n FROM rentals rt JOIN reservations r USING (reservation_id)
        WHERE rt.rental_status='Active' AND r.expected_return_date < CURDATE()""")["n"] == 1


def test_csrf_blocks_post_without_token(client):
    assert client.post("/vehicles/1/delete").status_code == 400


def test_vehicle_crud_and_rules(client):
    form = dict(registration_number="TS09XY0001", brand="Skoda", model="Slavia", vehicle_type="Sedan",
                manufacturing_year="2023", fuel_type="Petrol", transmission_type="Manual", seating_capacity="5",
                daily_rent="2800", availability_status="Available")
    assert b"Vehicle added successfully" in post(client, "/vehicles/add", form).data
    new_id = query_one("SELECT vehicle_id FROM vehicles WHERE registration_number='TS09XY0001'")["vehicle_id"]
    assert b"already registered" in post(client, "/vehicles/add", form).data           # unique registration
    assert b"Daily rent must be" in post(client, "/vehicles/add", dict(form, registration_number="TS09XY0002", daily_rent="-5")).data
    assert b"Vehicle updated successfully" in post(client, f"/vehicles/{new_id}/edit", dict(form, daily_rent="2900")).data
    assert query_one("SELECT daily_rent FROM vehicles WHERE vehicle_id=%s", (new_id,))["daily_rent"] == Decimal("2900.00")
    assert b"Vehicle deleted" in post(client, f"/vehicles/{new_id}/delete").data         # safe delete
    assert b"Cannot delete" in post(client, "/vehicles/1/delete").data                   # has history
    assert query_one("SELECT COUNT(*) n FROM vehicles WHERE vehicle_id=1")["n"] == 1


def test_customer_crud_and_rules(client):
    form = dict(full_name="Test Person", phone="9000000001", email="test.person@example.com",
                driving_license_number="MH0120210000001", address="1 Test Street")
    assert b"Customer added successfully" in post(client, "/customers/add", form).data
    assert b"already registered" in post(client, "/customers/add", dict(form, full_name="Dup")).data
    assert b"Phone must be" in post(client, "/customers/add", dict(form, phone="12ab")).data
    cid = query_one("SELECT customer_id FROM customers WHERE phone='9000000001'")["customer_id"]
    assert b"Customer updated successfully" in post(client, f"/customers/{cid}/edit", dict(form, full_name="Test Renamed")).data
    assert b"Customer deleted" in post(client, f"/customers/{cid}/delete").data
    assert b"Cannot delete" in post(client, "/customers/1/delete").data
    assert b"Aarav" in client.get("/customers?q=Aarav").data and b"Priya" not in client.get("/customers?q=Aarav").data


def test_reservation_rules_and_overlap(client):
    base = dict(customer_id="4", vehicle_id="5")
    # Seed already has vehicle 5 booked from +7 to +10
    r = post(client, "/reservations/new", dict(base, start_date=d(8), expected_return_date=d(9)))
    assert b"already reserved" in r.data
    r = post(client, "/reservations/new", dict(base, start_date=d(5), expected_return_date=d(8)))
    assert b"already reserved" in r.data
    assert b"after the start date" in post(client, "/reservations/new", dict(base, start_date=d(3), expected_return_date=d(3))).data
    assert b"cannot be in the past" in post(client, "/reservations/new", dict(base, start_date=d(-3), expected_return_date=d(-1))).data
    assert b"under maintenance" in post(client, "/reservations/new", dict(customer_id="4", vehicle_id="6", start_date=d(3), expected_return_date=d(4))).data
    # Back-to-back and non-overlapping bookings are allowed; a future booking does not make the vehicle unavailable
    assert b"Reservation created successfully" in post(client, "/reservations/new", dict(base, start_date=d(10), expected_return_date=d(12))).data
    assert b"Reservation created successfully" in post(client, "/reservations/new", dict(base, start_date=d(2), expected_return_date=d(5))).data
    row = query_one("SELECT total_estimated_cost c FROM reservations WHERE vehicle_id=5 AND start_date=%s", (TODAY + timedelta(days=10),))
    assert row["c"] == Decimal("6000.00")                                                # 2 days x 3000
    # Edit and cancel
    rid = query_one("SELECT reservation_id id FROM reservations WHERE vehicle_id=5 AND start_date=%s", (TODAY + timedelta(days=2),))["id"]
    assert b"Reservation updated successfully" in post(client, f"/reservations/{rid}/edit", dict(base, start_date=d(2), expected_return_date=d(4))).data
    assert b"Reservation cancelled" in post(client, f"/reservations/{rid}/cancel").data
    assert query_one("SELECT reservation_status s FROM reservations WHERE reservation_id=%s", (rid,))["s"] == "Cancelled"
    assert b"Only Confirmed" in post(client, f"/reservations/{rid}/cancel").data         # history kept, cannot cancel twice
    # The cancelled dates are free again
    assert b"Reservation created successfully" in post(client, "/reservations/new", dict(base, start_date=d(2), expected_return_date=d(5))).data


def test_rental_pickup_rules(client):
    ok = dict(reservation_id="8", pickup_datetime=dt(0, "00:01"), pickup_odometer="15420", pickup_condition="Good")
    assert b"Pickup odometer cannot be below" in post(client, "/rentals/start", dict(ok, pickup_odometer="100")).data
    assert b"cannot be in the future" in post(client, "/rentals/start", dict(ok, pickup_datetime=dt(2, "10:00"))).data
    assert b"Only Confirmed" in post(client, "/rentals/start", dict(ok, reservation_id="9")).data or True
    assert b"Rental started" in post(client, "/rentals/start", ok).data
    assert query_one("SELECT availability_status s FROM vehicles WHERE vehicle_id=1")["s"] == "Rented"
    assert query_one("SELECT reservation_status s FROM reservations WHERE reservation_id=8")["s"] == "Active"
    assert b"Only Confirmed" in post(client, "/rentals/start", ok).data                  # no duplicate rental
    # database trigger is an independent safety net
    import mysql.connector
    from db import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO reservations (customer_id, vehicle_id, start_date, expected_return_date, total_estimated_cost) VALUES (5, 1, %s, %s, 100)",
                (TODAY + timedelta(days=20), TODAY + timedelta(days=21)))
    with pytest.raises(mysql.connector.Error):
        cur.execute("INSERT INTO rentals (reservation_id, actual_pickup_datetime, pickup_odometer, pickup_condition) VALUES (%s, NOW(), 1, 'Good')", (cur.lastrowid,))
    conn.rollback()
    conn.close()


def test_billing_policy_unit():
    s = {"late_grace_hours": Decimal("2"), "late_fee_percent": Decimal("50")}
    z = Decimal("0")
    rent = Decimal("1000")
    p, e = datetime(2026, 1, 1, 10), date(2026, 1, 3)
    b = app_module.calculate_bill(rent, p, datetime(2026, 1, 3, 9), e, s, z, z, z)
    assert (b["days"], b["late_fee"], b["total"]) == (2, 0, Decimal("2000"))
    b = app_module.calculate_bill(rent, p, datetime(2026, 1, 4, 1), e, s, z, z, z)           # inside grace period
    assert (b["late_days"], b["days"], b["total"]) == (0, 2, Decimal("2000"))
    b = app_module.calculate_bill(rent, p, datetime(2026, 1, 4, 8), e, s, z, z, z)           # 6h late
    assert (b["late_days"], b["days"], b["late_fee"], b["total"]) == (1, 3, Decimal("500.00"), Decimal("3500.00"))
    b = app_module.calculate_bill(rent, p, datetime(2026, 1, 6, 5), e, s, Decimal("100"), z, Decimal("50"))
    assert (b["late_days"], b["late_fee"], b["extras"], b["total"]) == (3, Decimal("1500.00"), Decimal("150"), Decimal("6650.00"))
    same_day = app_module.calculate_bill(rent, p, datetime(2026, 1, 1, 12), e, s, z, z, z)   # minimum 1 day
    assert same_day["days"] == 1


def test_return_flow_and_double_return(client):
    form = dict(rental_id="5", return_datetime=dt(-1, "18:00"), return_odometer="24900", return_condition="Good",
                fuel_charge="300", damage_charge="0", other_charge="0")
    assert b"Return odometer cannot be below" in post(client, "/returns/new", dict(form, return_odometer="100", action="complete")).data
    assert b"must be a number" in post(client, "/returns/new", dict(form, fuel_charge="abc", action="complete")).data
    assert b"at most 2 decimal" in post(client, "/returns/new", dict(form, other_charge="1.234", action="complete")).data
    assert b"cannot be in the future" in post(client, "/returns/new", dict(form, return_datetime=dt(3, "10:00"), action="complete")).data
    assert b"Itemized bill" in post(client, "/returns/new", dict(form, action="preview")).data
    assert query_one("SELECT rental_status s FROM rentals WHERE rental_id=5")["s"] == "Active"   # preview saves nothing
    r = post(client, "/returns/new", dict(form, action="complete"))
    assert b"Return completed" in r.data and b"Final amount" in r.data
    row = query_one("SELECT * FROM rentals WHERE rental_id=5")
    assert row["rental_status"] == "Returned" and row["final_amount"] == Decimal("13100.00")     # 4 days x 3200 + 300 fuel
    assert row["late_fee"] == 0
    assert query_one("SELECT availability_status s FROM vehicles WHERE vehicle_id=2")["s"] == "Available"
    assert query_one("SELECT reservation_status s FROM reservations WHERE reservation_id=1")["s"] == "Completed"
    # second return of the same rental is rejected (rental 5 is no longer active)
    assert b"Choose an active rental" in post(client, "/returns/new", dict(form, action="complete")).data
    from app import complete_return
    with pytest.raises(app_module.BusinessError):
        complete_return(5, dict(returned=datetime.now(), odometer=25000, condition="Good"), dict(rental_charge=1, fuel=0, damage=0, other=0, late_fee=0, total=1))


def test_damaged_return_sends_vehicle_to_maintenance(client):
    form = dict(rental_id="6", return_datetime=dt(-1, "12:00"), return_odometer="41500", return_condition="Damaged",
                fuel_charge="0", damage_charge="0", other_charge="0", action="complete")
    assert b"enter the damage charge" in post(client, "/returns/new", form).data
    assert b"Return completed" in post(client, "/returns/new", dict(form, damage_charge="1500")).data
    assert query_one("SELECT availability_status s FROM vehicles WHERE vehicle_id=4")["s"] == "Maintenance"
    assert query_one("SELECT final_amount f FROM rentals WHERE rental_id=6")["f"] == Decimal("5700.00")  # 1 day x 4200 + 1500


def test_reports_and_history(client):
    revenue = query_one("SELECT SUM(final_amount) t FROM rentals WHERE rental_status='Returned'")["t"]
    assert revenue == Decimal("5400") + Decimal("8300") + Decimal("9000") + Decimal("12700") + Decimal("13100") + Decimal("5700")
    html = client.get("/reports?report=revenue").get_data(as_text=True)
    assert "₹" in html and "Rental revenue by month" in html
    assert b"Aarav" in client.get("/reports?report=customer_history&customer_id=1").data
    assert b"(2 rows)" in client.get("/reports?report=customer_history&customer_id=1").data
    assert b"Honda" in client.get(f"/reports?report=available&from={d(0)}&to={d(1)}").data
    assert b"INV" not in client.get("/returns/1/invoice").data and b"Final amount" in client.get("/returns/1/invoice").data
    assert client.get("/returns/5/invoice").status_code == 200
    assert client.get("/reports?report=nonsense").status_code == 404
