import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Stores last detected barcode
last_result = {"barcode": None}

# OpenCV barcode detector
detector = cv2.barcode_BarcodeDetector()

@app.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    global last_result

    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image received"}), 400

        # Convert bytes → OpenCV image
        img_np = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # ---- Safe decode handling for all OpenCV builds ----
        result = detector.detectAndDecode(frame)

        # OpenCV 4.8+ returns 4 items / older returns 3
        if len(result) == 4:
            ok, decoded_info, decoded_type, points = result
        elif len(result) == 3:
            decoded_info, decoded_type, points = result
            ok = len(decoded_info) > 0
        else:
            return jsonify({"success": False, "message": "Unexpected decode output"}), 500

        # ---- If barcode found ----
        if ok and decoded_info:
            barcode = decoded_info[0]
            last_result["barcode"] = barcode
            return jsonify({"success": True, "barcode": barcode}), 200

        # ---- If no barcode ----
        last_result["barcode"] = None
        return jsonify({"success": False, "message": "No barcode detected"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/result', methods=['GET'])
def result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
