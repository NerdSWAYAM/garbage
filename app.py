import io
from PIL import Image
from flask import Flask, render_template, request, jsonify
from model.cnn_model import predict_image

app = Flask(__name__, template_folder='template')

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

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(debug=True)