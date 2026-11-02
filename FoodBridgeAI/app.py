
import os
import sqlite3

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)


# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "foodbridge-ai-secret-key"


# Database connection
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


# Create database tables
def create_database():

    with get_db_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donor_id INTEGER NOT NULL,
                food_name TEXT NOT NULL,
                quantity TEXT NOT NULL,
                location TEXT NOT NULL,
                expiry_time TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'Available',
                FOREIGN KEY (donor_id) REFERENCES users(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS food_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donation_id INTEGER NOT NULL,
                ngo_id INTEGER NOT NULL,
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (donation_id) REFERENCES donations(id),
                FOREIGN KEY (ngo_id) REFERENCES users(id),
                UNIQUE(donation_id, ngo_id)
            )
        """)


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# Registration
@app.route("/register", methods=["GET", "POST"])
def register():

    message = ""

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        if not name or not email or not password or role not in ["donor", "ngo"]:
            message = "Please fill in all fields correctly."

        else:
            hashed_password = generate_password_hash(password)

            try:
                with get_db_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO users (name, email, password, role)
                        VALUES (?, ?, ?, ?)
                        """,
                        (name, email, hashed_password, role)
                    )

                message = "Registration successful! Please login."

            except sqlite3.IntegrityError:
                message = "This email is already registered."

    return render_template("register.html", message=message)


# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    message = ""

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            return redirect(url_for("dashboard"))

        message = "Invalid email or password."

    return render_template("login.html", message=message)


# Dashboard
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == "donor":
        return render_template("donor.html", name=session["name"])

    if session["role"] == "ngo":
        return render_template("ngo.html", name=session["name"])

    return redirect(url_for("logout"))


# Donor - Add food donation
@app.route("/add-donation", methods=["GET", "POST"])
def add_donation():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "donor":
        return redirect(url_for("dashboard"))

    message = ""

    if request.method == "POST":

        food_name = request.form.get("food_name", "").strip()
        quantity = request.form.get("quantity", "").strip()
        location = request.form.get("location", "").strip()
        expiry_time = request.form.get("expiry_time", "").strip()
        description = request.form.get("description", "").strip()

        if not all([food_name, quantity, location, expiry_time]):
            message = "Please fill in all required fields."

        else:
            with get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO donations
                    (donor_id, food_name, quantity, location,
                     expiry_time, description)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session["user_id"],
                        food_name,
                        quantity,
                        location,
                        expiry_time,
                        description
                    )
                )

            message = "Food donation added successfully!"

    return render_template("add_donation.html", message=message)


# Donor - View own donations
@app.route("/my-donations")
def my_donations():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "donor":
        return redirect(url_for("dashboard"))

    with get_db_connection() as conn:

        donations = conn.execute(
            """
            SELECT * FROM donations
            WHERE donor_id = ?
            ORDER BY id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    return render_template(
        "my_donations.html",
        donations=donations
    )


# NGO - View available food
@app.route("/available-food")
def available_food():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "ngo":
        return redirect(url_for("dashboard"))

    with get_db_connection() as conn:

        donations = conn.execute(
            """
            SELECT donations.*, users.name AS donor_name
            FROM donations
            JOIN users ON donations.donor_id = users.id
            WHERE donations.status = 'Available'
            ORDER BY donations.id DESC
            """
        ).fetchall()

    return render_template(
        "available_food.html",
        donations=donations,
        name=session["name"]
    )


# NGO - Request food
@app.route("/request-food/<int:donation_id>", methods=["POST"])
def request_food(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "ngo":
        return redirect(url_for("dashboard"))

    try:
        with get_db_connection() as conn:

            donation = conn.execute(
                """
                SELECT id FROM donations
                WHERE id = ? AND status = 'Available'
                """,
                (donation_id,)
            ).fetchone()

            if donation:
                conn.execute(
                    """
                    INSERT INTO food_requests (donation_id, ngo_id)
                    VALUES (?, ?)
                    """,
                    (donation_id, session["user_id"])
                )

                flash("Food request submitted successfully!")

            else:
                flash("This food donation is no longer available.")

    except sqlite3.IntegrityError:
        flash("You have already requested this food.")

    return redirect(url_for("available_food"))


# NGO - My requests
@app.route("/my-requests")
def my_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "ngo":
        return redirect(url_for("dashboard"))

    with get_db_connection() as conn:

        requests_data = conn.execute(
            """
            SELECT
                food_requests.id AS request_id,
                donations.food_name,
                donations.quantity,
                donations.location,
                donations.expiry_time,
                food_requests.status,
                users.name AS donor_name
            FROM food_requests
            JOIN donations
                ON food_requests.donation_id = donations.id
            JOIN users
                ON donations.donor_id = users.id
            WHERE food_requests.ngo_id = ?
            ORDER BY food_requests.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    return render_template(
        "my_requests.html",
        requests_data=requests_data
    )


# NGO - Food collection
@app.route("/food-collection")
def food_collection():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] != "ngo":
        return redirect(url_for("dashboard"))

    with get_db_connection() as conn:

        collection_data = conn.execute(
            """
            SELECT
                donations.food_name,
                donations.quantity,
                donations.location,
                donations.expiry_time,
                users.name AS donor_name
            FROM food_requests
            JOIN donations
                ON food_requests.donation_id = donations.id
            JOIN users
                ON donations.donor_id = users.id
            WHERE food_requests.ngo_id = ?
            AND food_requests.status = 'Accepted'
            ORDER BY food_requests.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    return render_template(
        "food_collection.html",
        collection_data=collection_data
    )


# Logout
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


if __name__ == "__main__":

    create_database()

    app.run(debug=True)
