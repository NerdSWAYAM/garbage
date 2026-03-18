import io
from PIL import Image
import psycopg2
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from model.cnn_model import predict_image

app = Flask(__name__, template_folder='template')
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key

#database connection 
def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        dbname="garbage_db",   # change if needed
        user="postgres",
        password="sage666",
        port=6969
    )

#table creation
def create_table():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            firstname VARCHAR(250) NOT NULL,
            lastname VARCHAR(250) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL
        );
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("Table created or already exists.")
    except Exception as e:
        print(f"Database connection error: {e}")

create_table()

@app.route("/")
def waste_classifier():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    
    try:
        # Read the file and convert to an image
        img_bytes = file.read()
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        
        # Pass the image to the huggingface pipeline
        result = predict_image(image)
        
        # Load impact info
        impact_info = None
        try:
            import json
            with open("impact.json", "r") as f:
                impact_data = json.load(f)
            
            # Case-insensitive lookup
            for key, val in impact_data.items():
                if key.lower() == result.lower():
                    impact_info = val
                    break
        except Exception as json_e:
            print("Impact lookup error:", json_e)
            
        return jsonify({"prediction": result, "impact": impact_info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/map")
def map_page():
    return render_template("map.html")

#login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template("login.html")  # show page

    # POST logic
    email = request.form['email']
    password = request.form['password']

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cur.fetchone()

    cur.close()
    conn.close()

    if user and check_password_hash(user[3], password):
        session['user'] = email
        return redirect(url_for('dashboard'))   # ✅ FIX
    else:
        return "<h2>Invalid Email or Password</h2>"
    
#Regitration route 
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])  # 🔐 secure

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (firstname, lastname, email, password) VALUES (%s,%s,%s,%s)",
                (firstname, lastname, email, password)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            return "<h3>Email already exists </h3>"
        finally:
            cur.close()
            conn.close()

        return render_template('/login.html')

    return render_template("register.html")


@app.route("/dashboard")
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template("dashboard.html")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('waste_classifier'))

if __name__ == "__main__":
    app.run(debug=True)