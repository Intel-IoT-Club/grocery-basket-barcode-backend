import eventlet
eventlet.monkey_patch()

import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import base64

app = Flask(__name__)
CORS(app)

# Globals for barcode decoding
barcode_detector = cv2.barcode_BarcodeDetector()
last_processed_barcode = None
last_processed_time = 0
processing_cooldown = 5  # seconds

def detect_barcodes(frame):
    """
    Detect barcodes in frame, handling different OpenCV versions
    """
    try:
        result = barcode_detector.detectAndDecode(frame)
        print(f"OpenCV detectAndDecode returned: {len(result)} values")
        
        # Handle different return formats
        if len(result) == 4:
            # Newer OpenCV: (ok, decoded_info, decoded_type, corners)
            ok, decoded_info, decoded_type, corners = result
            print(f"New format - OK: {ok}, Decoded: {decoded_info}, Type: {decoded_type}")
        elif len(result) == 3:
            # Older OpenCV: (ok, decoded_info, corners)
            ok, decoded_info, corners = result
            print(f"Old format - OK: {ok}, Decoded: {decoded_info}")
        else:
            # Unknown format
            print(f"Unknown format: {result}")
            return False, []
            
        return ok, decoded_info
        
    except Exception as e:
        print(f"Barcode detection error: {e}")
        return False, []

@app.route('/api/upload_frame', methods=['POST'])
def handle_frame_upload():
    """
    Input endpoint: Accepts image frames and detects barcodes
    """
    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image data"}), 400

        print(f"Received image data: {len(img_data)} bytes")
        
        # Decode image
        img_np = np.frombuffer(img_data, dtype=np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        
        if frame is None:
            print("Failed to decode image")
            return jsonify({"success": False, "message": "Failed to decode image"}), 400

        print(f"Decoded image shape: {frame.shape}")
        
        # Detect barcodes
        ok, decoded_info = detect_barcodes(frame)
        
        print(f"Detection result - OK: {ok}, Decoded info: {decoded_info}")
        
        if ok and decoded_info and len(decoded_info) > 0:
            barcode_data = decoded_info[0].strip()
            print(f"Raw barcode data: '{barcode_data}'")
            
            if barcode_data:
                # Process the barcode data
                global last_processed_barcode, last_processed_time
                current_time = time.time()
                
                # Check cooldown
                if barcode_data == last_processed_barcode and (current_time - last_processed_time) < processing_cooldown:
                    return jsonify({"success": False, "message": "Barcode already processed recently"}), 202
                
                # Update last processed barcode
                last_processed_barcode = barcode_data
                last_processed_time = current_time
                
                return jsonify({
                    "success": True, 
                    "barcode_data": barcode_data, 
                    "message": "Barcode detected successfully"
                }), 200
            else:
                return jsonify({"success": False, "message": "Empty barcode data"}), 200
        else:
            return jsonify({"success": False, "message": "No barcode detected"}), 200

    except Exception as e:
        print(f"Error in /api/upload_frame: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/result', methods=['GET'])
def get_barcode_result():
    """
    Output endpoint: Returns the last processed barcode data
    """
    if last_processed_barcode:
        return jsonify({
            "success": True,
            "barcode_data": last_processed_barcode,
            "timestamp": last_processed_time,
            "message": "Barcode data retrieved successfully"
        }), 200
    else:
        return jsonify({
            "success": False,
            "barcode_data": None,
            "message": "No barcode has been processed yet"
        }), 404

@app.route('/debug', methods=['POST'])
def debug_image():
    """
    Debug endpoint to check image reception
    """
    try:
        img_data = request.data
        print(f"Debug - Received {len(img_data)} bytes")
        
        # Try to decode and get basic info
        img_np = np.frombuffer(img_data, dtype=np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        
        if frame is not None:
            return jsonify({
                "success": True,
                "message": f"Image decoded successfully: {frame.shape}",
                "shape": frame.shape
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "Failed to decode image"
            }), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Debug error: {str(e)}"
        }), 500

if __name__ == '__main__':
    print("Starting Barcode Reader Server...")
    print("Available endpoints:")
    print("  POST /api/upload_frame - Upload image frame for barcode detection")
    print("  POST /debug - Debug image upload")
    print("  GET  /result - Get the last detected barcode")
    app.run(host='0.0.0.0', port=5000, debug=False)