import cv2
import numpy as np
import pytesseract
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

last_result = {"barcode": None}

detector = cv2.barcode_BarcodeDetector()


# ----------------------------
# IMAGE ENHANCEMENT
# ----------------------------
def enhance(frame):
    frame = cv2.resize(frame, None, fx=2.0, fy=2.0)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Noise removal
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Sharpen
    kernel = np.array([[0, -1, 0],
                       [-1, 5,-1],
                       [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    # Contrast boost
    gray = cv2.equalizeHist(gray)

    return gray


# ----------------------------
# TRY BARCODE DETECTOR FIRST
# ----------------------------
def try_opencv(gray):
    result = detector.detectAndDecode(gray)

    if len(result) == 4:
        ok, decoded_info, decoded_type, points = result
    else:
        decoded_info, decoded_type, points = result
        ok = decoded_info and len(decoded_info) > 0

    if ok and decoded_info:
        return decoded_info[0]

    return None


# ----------------------------
# OCR FALLBACK – READ DIGITS BELOW THE BARCODE
# ----------------------------
def try_ocr(frame):
    # Crop bottom 35% (where barcode digits usually are)
    h, w = frame.shape[:2]
    crop = frame[int(h * 0.60):h, 0:w]

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # OCR only digits
    text = pytesseract.image_to_string(gray, config="--psm 6 -c tessedit_char_whitelist=0123456789")
    text = "".join([c for c in text if c.isdigit()])

    # Valid product barcodes are 11–14 digits
    if len(text) >= 11:
        return text

    return None


@app.route("/api/upload_frame", methods=["POST"])
def upload_frame():
    global last_result

    try:
        raw = request.data
        if not raw:
            return jsonify({"success": False, "message": "No image"}), 400

        # Decode image
        arr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # Enhance first
        gray = enhance(frame)

        # Try OpenCV detector
        barcode = try_opencv(gray)

        # If OpenCV returns 1 digit or fails → OCR fallback
        if not barcode or len(barcode) <= 3:
            barcode = try_ocr(frame)

        # Final check
        if not barcode:
            last_result = {"barcode": None}
            return jsonify({"success": False, "message": "No barcode detected"}), 200

        last_result = {"barcode": barcode}
        return jsonify({"success": True, "barcode": barcode})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/result", methods=["GET"])
def result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
