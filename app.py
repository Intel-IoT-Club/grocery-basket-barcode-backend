import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from pyzxing import BarCodeReader

app = Flask(__name__)
CORS(app)

last_result = {"barcode": None, "type": None}

# OpenCV detector
detector = cv2.barcode_BarcodeDetector()

# ZXing reader (fallback)
zxing_reader = BarCodeReader()

def enhance_image(frame):
    """Improve barcode readability"""
    # Resize (2x)
    frame = cv2.resize(frame, None, fx=2.0, fy=2.0)

    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Increase contrast
    gray = cv2.equalizeHist(gray)

    return gray


def try_opencv(gray):
    """Try decoding using OpenCV"""
    result = detector.detectAndDecode(gray)

    if len(result) == 4:
        ok, decoded_info, decoded_type, points = result
    else:
        decoded_info, decoded_type, points = result
        ok = len(decoded_info) > 0

    if ok and decoded_info:
        return decoded_info[0], decoded_type[0] if decoded_type else "unknown"

    return None, None


def try_zxing(frame):
    """Try ZXing fallback"""
    # Save frame temporarily
    temp_path = "/tmp/frame.png"
    cv2.imwrite(temp_path, frame)

    out = zxing_reader.decode(temp_path)

    if out and len(out) > 0:
        return out[0].get("raw", None), out[0].get("format", None)

    return None, None


@app.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    global last_result

    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image data"}), 400

        img_np = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # -- Step 1: Enhance image --
        gray = enhance_image(frame)

        # -- Step 2: Try OpenCV --
        barcode, code_type = try_opencv(gray)

        # -- Step 3: If OpenCV fails, fallback to ZXing --
        if not barcode:
            barcode, code_type = try_zxing(frame)

        # -- Step 4: No barcode found --
        if not barcode:
            last_result = {"barcode": None, "type": None}
            return jsonify({"success": False, "message": "No barcode detected"}), 200

        # -- Step 5: Success --
        last_result = {"barcode": barcode, "type": code_type}

        return jsonify({
            "success": True,
            "barcode": barcode,
            "type": code_type
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/result', methods=['GET'])
def get_result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
