import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

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

        img_np = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        ok, decoded_info, _, _ = detector.detectAndDecode(frame)

        if ok and decoded_info:
            barcode = decoded_info[0]
            last_result["barcode"] = barcode
            return jsonify({"success": True, "barcode": barcode}), 200

        last_result["barcode"] = None
        return jsonify({"success": False, "message": "No barcode detected"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/result', methods=['GET'])
def result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
