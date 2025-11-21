import cv2
import numpy as np
# Use pyzbar for barcode decoding (works for 1D barcodes and QR codes)
from pyzbar.pyzbar import decode 
from flask import Flask, request, jsonify
import time

# Flask application instance
app = Flask(__name__)

# Global variable to store the latest decoded barcode result
latest_barcode_result = {
    "data": "No barcode scanned yet.",
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
}

# Cooldown mechanism to prevent rapid duplicate scans
last_scan_time = 0
COOLDOWN_SECONDS = 3

# --- Core Logic for Barcode Decoding ---
def decode_barcode_from_frame(frame):
    """
    Decodes barcodes using pyzbar.
    Returns the decoded data (string) or None.
    """
    global latest_barcode_result, last_scan_time
    
    current_time = time.time()
    
    # Apply a global cooldown
    if (current_time - last_scan_time) < COOLDOWN_SECONDS:
        print("Scan ignored (global cooldown active).")
        return None
        
    # Decode any barcodes present in the frame
    decoded_objects = decode(frame)
    
    if decoded_objects:
        # Get the data from the first detected barcode
        barcode_data_bytes = decoded_objects[0].data
        barcode_data = barcode_data_bytes.decode('utf-8')
        
        # Check for immediate duplicates based on data and cooldown
        if barcode_data == latest_barcode_result['data'] and (current_time - last_scan_time) < 15:
            print(f"Duplicate scan for {barcode_data}. Ignoring.")
            return None
        
        # Update the global result and reset cooldown
        latest_barcode_result = {
            "data": barcode_data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        last_scan_time = current_time
        print(f"Barcode Decoded: {barcode_data}")
        return barcode_data
        
    return None

# --- API Endpoint to Receive Frame from ESP32-CAM ---
# The ESP32-CAM should POST binary JPEG image data to this endpoint.
@app.route('/api/upload_frame', methods=['POST'])
def handle_frame_upload():
    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image data received"}), 400

        # Convert binary data to a NumPy array and decode it into an OpenCV frame
        img_np = np.frombuffer(img_data, dtype=np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        
        if frame is None:
             return jsonify({"success": False, "message": "Failed to decode image"}), 400
        
        decoded_data = decode_barcode_from_frame(frame)
        
        if decoded_data:
            return jsonify({"success": True, "message": "Barcode detected and decoded.", "data": decoded_data}), 200
        else:
            return jsonify({"success": False, "message": "No new barcode detected (or cooldown active)."}), 202 # Use 202 Accepted if scan is ignored

    except Exception as e:
        print(f"Error in /api/upload_frame: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

# --- API Endpoint to Display Result ---
# This is the endpoint the front-end will check for the latest result.
@app.route('/result', methods=['GET'])
def get_latest_result():
    """Displays the latest decoded barcode data."""
    return jsonify(latest_barcode_result)

# Render runs this file by importing the 'app' variable, so no __name__ == '__main__': is needed.