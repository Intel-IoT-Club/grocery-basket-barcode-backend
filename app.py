import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from pyzbar.pyzbar import decode

app = Flask(__name__)
CORS(app)

# Store last detected barcode
last_result = {"barcode": None}

@app.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    global last_result
    
    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image received"}), 400

        # Convert raw bytes → OpenCV image
        img_np = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # Decode barcode
        barcodes = decode(frame)

        if not barcodes:
            last_result["barcode"] = None
            return jsonify({"success": False, "message": "No barcode detected"}), 200

        # Take first detected barcode
        barcode_value = barcodes[0].data.decode("utf-8")
        last_result["barcode"] = barcode_value

        return jsonify({"success": True, "barcode": barcode_value}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/result', methods=['GET'])
def get_result():
    return jsonify(last_result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
