import io
import psycopg2
from PIL import Image
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sys
import os

# ─── Model Import ────────────────────────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    volo_test = __import__("volo-test")
    predict_waste = volo_test.predict_waste
except Exception:
    from model.cnn_model import predict_image as predict_waste

# ─── App Setup ───────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder='template')
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

# ─── Waste Impact Data ───────────────────────────────────────────────────────
# Maps prediction labels → environmental info shown in the UI result card
WASTE_IMPACT = {
    "plastic":        {"category": "Recyclable",  "co2_emission": "~6 kg CO₂/kg", "recycle": "Yes ✓",  "disposal": "Yellow recycling bin"},
    "paper":          {"category": "Recyclable",  "co2_emission": "~1 kg CO₂/kg", "recycle": "Yes ✓",  "disposal": "Blue paper bin"},
    "cardboard":      {"category": "Recyclable",  "co2_emission": "~1 kg CO₂/kg", "recycle": "Yes ✓",  "disposal": "Blue paper bin"},
    "metal":          {"category": "Recyclable",  "co2_emission": "~2 kg CO₂/kg", "recycle": "Yes ✓",  "disposal": "Metal recycling bin"},
    "glass":          {"category": "Recyclable",  "co2_emission": "~0.9 kg CO₂/kg","recycle": "Yes ✓", "disposal": "Glass bottle bank"},
    "organic":        {"category": "Organic",     "co2_emission": "~0.5 kg CO₂/kg","recycle": "Compost","disposal": "Green compost bin"},
    "food":           {"category": "Organic",     "co2_emission": "~0.5 kg CO₂/kg","recycle": "Compost","disposal": "Green compost bin"},
    "battery":        {"category": "Hazardous",   "co2_emission": "High",          "recycle": "Special","disposal": "Hazardous waste centre"},
    "electronic":     {"category": "E-Waste",     "co2_emission": "High",          "recycle": "Special","disposal": "E-waste collection point"},
    "hazardous":      {"category": "Hazardous",   "co2_emission": "High",          "recycle": "No ✗",   "disposal": "Hazardous waste centre"},
    "medical":        {"category": "Hazardous",   "co2_emission": "High",          "recycle": "No ✗",   "disposal": "Pharmacy / medical waste"},
    "general":        {"category": "General",     "co2_emission": "~0.5 kg CO₂/kg","recycle": "No ✗",  "disposal": "Black general waste bin"},
    "trash":          {"category": "General",     "co2_emission": "~0.5 kg CO₂/kg","recycle": "No ✗",  "disposal": "Black general waste bin"},
}

def get_impact(prediction: str) -> dict:
    """Return impact data for a prediction label, falling back to 'general'."""
    key = prediction.lower()
    for k, v in WASTE_IMPACT.items():
        if k in key:
            return v
    return WASTE_IMPACT["general"]


# ─── Database ────────────────────────────────────────────────────────────────
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        dbname=os.environ.get('DB_NAME', 'garbage_db'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASSWORD', 'sage666'),
        port=int(os.environ.get('DB_PORT', 6969))
    )


def create_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                firstname  VARCHAR(250) NOT NULL,
                lastname   VARCHAR(250) NOT NULL,
                email      VARCHAR(100) UNIQUE NOT NULL,
                password   VARCHAR(255) NOT NULL,
                location   VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add location column if upgrading from old schema (safe to run repeatedly)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS location VARCHAR(255);
        """)
        cur.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id        SERIAL PRIMARY KEY,
                email     VARCHAR(100),
                category  VARCHAR(100),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
            );
        """)

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[DB] Table creation error: {e}")


create_tables()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("index.html")


# ── Prediction ───────────────────────────────────────────────────────────────

@app.route("/predict", methods=["POST"])
def predict():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        img_bytes = file.read()
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        result = predict_waste(image)

        # Save to history if user is logged in and a real result
        if result and result != "No waste detected" and 'user' in session:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO history (email, category) VALUES (%s, %s)",
                (session['user'], result)
            )
            conn.commit()
            cur.close()
            conn.close()

        # Build impact payload for the UI result card
        impact = get_impact(result)

        return jsonify({
            "prediction": result,
            "impact": impact
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Map ──────────────────────────────────────────────────────────────────────

@app.route("/map")
def map_page():
    return render_template("map.html")


# ── Login ────────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")

    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '')

    if not email or not password:
        return render_template("login.html", error="Please fill in all fields.")

    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return render_template("login.html", error=f"Database error: {e}")

    # user row: (firstname, lastname, email, password, location, created_at)
    # password is at index 3
    if user and check_password_hash(user[3], password):
        session['user']      = email
        session['firstname'] = user[0]
        session['lastname']  = user[1]
        return redirect(url_for('dashboard'))

    return render_template("login.html", error="Invalid email or password.")


# ── Register ─────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template("register.html")

    firstname = request.form.get('firstname', '').strip()
    lastname  = request.form.get('lastname', '').strip()
    email     = request.form.get('email', '').strip()
    password  = request.form.get('password', '')
    location  = request.form.get('location', '').strip()

    if not all([firstname, lastname, email, password]):
        return render_template("register.html", error="Please fill in all required fields.")

    hashed_pw = generate_password_hash(password)

    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO users (firstname, lastname, email, password, location) VALUES (%s,%s,%s,%s,%s)",
            (firstname, lastname, email, hashed_pw, location or None)
        )
        conn.commit()
        cur.close()
        conn.close()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        cur.close()
        conn.close()
        return render_template("register.html", error="An account with this email already exists.")
    except Exception as e:
        try:
            conn.rollback()
            cur.close()
            conn.close()
        except Exception:
            pass
        return render_template("register.html", error=f"Registration failed: {e}")

    return redirect(url_for('login'))


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        cur  = conn.cursor()

        # Chart data — category counts
        cur.execute("""
            SELECT category, COUNT(*)
            FROM history
            WHERE email = %s
            GROUP BY category
            ORDER BY COUNT(*) DESC
        """, (session['user'],))
        chart_data = cur.fetchall()

        labels = [row[0] for row in chart_data]
        values = [row[1] for row in chart_data]

        # Recent scan history (last 5)
        cur.execute("""
            SELECT category, timestamp
            FROM history
            WHERE email = %s
            ORDER BY timestamp DESC
            LIMIT 5
        """, (session['user'],))
        history = cur.fetchall()

        # Total scans count
        cur.execute("SELECT COUNT(*) FROM history WHERE email = %s", (session['user'],))
        total_scans = cur.fetchone()[0]

        cur.close()
        conn.close()
    except Exception as e:
        labels = []
        values = []
        history = []
        total_scans = 0
        print(f"[Dashboard] DB error: {e}")

    return render_template(
        "dashboard.html",
        labels=labels,
        values=values,
        history=history,
        total_scans=total_scans,
    )


# ── Forgot Password ──────────────────────────────────────────────────────────

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template("forgot.html")

    email        = request.form.get('email', '').strip()
    new_password = request.form.get('password', '')

    if not email or not new_password:
        return render_template("forgot.html", error="Please fill in all fields.")

    try:
        conn = get_db_connection()
        cur  = conn.cursor()

        # Check email actually exists before updating
        cur.execute("SELECT email FROM users WHERE email = %s", (email,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return render_template("forgot.html", error="No account found with that email address.")

        cur.execute(
            "UPDATE users SET password = %s WHERE email = %s",
            (generate_password_hash(new_password), email)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        return render_template("forgot.html", error=f"Error: {e}")

    return redirect(url_for('login'))


# ── Logout ───────────────────────────────────────────────────────────────────

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)