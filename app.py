import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

last_result = {"barcode": None}

detector = cv2.barcode_BarcodeDetector()

def enhance(frame):
    # Resize (2x)
    frame = cv2.resize(frame, None, fx=2.0, fy=2.0)

    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Sharpen
    kernel = np.array([[0, -1, 0],
                       [-1, 5,-1],
                       [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    # Increase contrast
    gray = cv2.equalizeHist(gray)

    return gray


def safe_decode(gray):
    result = detector.detectAndDecode(gray)

    # Handle both OpenCV return formats
    if len(result) == 4:
        ok, decoded_info, decoded_type, points = result
    else:
        decoded_info, decoded_type, points = result
        ok = decoded_info is not None and len(decoded_info) > 0

    if ok and decoded_info:
        return decoded_info[0]

    return None


@app.route("/api/upload_frame", methods=["POST"])
def upload_frame():
    global last_result

    try:
        data = request.data
        if not data:
            return jsonify({"success": False, "message": "No image"}), 400

        img_np = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # Enhance before decoding
        gray = enhance(frame)

        barcode = safe_decode(gray)

        if not barcode:
            last_result = {"barcode": None}
            return jsonify({"success": False, "message": "No barcode detected"}), 200

        last_result = {"barcode": barcode}
        return jsonify({"success": True, "barcode": barcode}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/result", methods=["GET"])
def result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
