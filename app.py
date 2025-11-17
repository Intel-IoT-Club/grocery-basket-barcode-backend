import eventlet
eventlet.monkey_patch()

import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# Globals for barcode decoding
barcode_detector = cv2.barcode_BarcodeDetector()
last_processed_barcode = None
last_processed_time = 0
processing_cooldown = 5  # seconds

def read_barcodes_opencv(frame):
    """
    Read barcodes using OpenCV's barcode detector
    Similar to your working pyzbar code
    """
    try:
        # Detect and decode barcodes
        result = barcode_detector.detectAndDecode(frame)
        
        # Handle different OpenCV return formats
        if len(result) == 4:
            # Newer OpenCV: (ok, decoded_info, decoded_type, corners)
            ok, decoded_info, decoded_type, corners = result
        elif len(result) == 3:
            # Older OpenCV: (ok, decoded_info, corners)  
            ok, decoded_info, corners = result
        else:
            return []
        
        barcodes = []
        if ok and decoded_info:
            for i, barcode_data in enumerate(decoded_info):
                barcode_text = barcode_data.strip()
                if barcode_text:
                    # Get bounding box if available
                    bbox = None
                    if corners is not None and i < len(corners):
                        bbox = corners[i]
                    
                    barcodes.append({
                        'data': barcode_text,
                        'bbox': bbox
                    })
                    print(f"Detected barcode: {barcode_text}")
        
        return barcodes
        
    except Exception as e:
        print(f"Error in barcode detection: {e}")
        return []

def preprocess_frame(frame):
    """
    Preprocess frame to improve barcode detection
    """
    # Convert to grayscale (like many barcode detectors prefer)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Try multiple preprocessing techniques
    processed_frames = []
    
    # 1. Original grayscale
    processed_frames.append(("grayscale", gray))
    
    # 2. Resize if image is too large
    height, width = gray.shape
    if width > 800:
        new_width = 800
        new_height = int((new_width / width) * height)
        resized = cv2.resize(gray, (new_width, new_height))
        processed_frames.append(("resized", resized))
    
    # 3. Apply mild blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    processed_frames.append(("blurred", blurred))
    
    # 4. Increase contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    contrast = clahe.apply(gray)
    processed_frames.append(("contrast", contrast))
    
    return processed_frames

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
        
        # Try multiple preprocessing techniques
        processed_frames = preprocess_frame(frame)
        detected_barcodes = []
        
        for method_name, processed_frame in processed_frames:
            print(f"Trying detection with: {method_name}")
            barcodes = read_barcodes_opencv(processed_frame)
            if barcodes:
                detected_barcodes.extend(barcodes)
                print(f"Found {len(barcodes)} barcodes with {method_name}")
        
        # Remove duplicates
        unique_barcodes = []
        seen_barcodes = set()
        for barcode in detected_barcodes:
            if barcode['data'] not in seen_barcodes:
                unique_barcodes.append(barcode)
                seen_barcodes.add(barcode['data'])
        
        if unique_barcodes:
            # Use the first detected barcode
            barcode_data = unique_barcodes[0]['data']
            print(f"Final barcode data: '{barcode_data}'")
            
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
                "message": "Barcode detected successfully",
                "total_found": len(unique_barcodes)
            }), 200
        else:
            print("No barcodes detected after trying all methods")
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
    Debug endpoint to check image reception and basic barcode detection
    """
    try:
        img_data = request.data
        print(f"Debug - Received {len(img_data)} bytes")
        
        # Try to decode and get basic info
        img_np = np.frombuffer(img_data, dtype=np.uint8)
        frame = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
        
        if frame is not None:
            # Try basic barcode detection
            barcodes = read_barcodes_opencv(frame)
            
            return jsonify({
                "success": True,
                "message": f"Image decoded successfully: {frame.shape}",
                "shape": frame.shape,
                "barcodes_found": len(barcodes),
                "barcodes": [b['data'] for b in barcodes]
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

@app.route('/test', methods=['GET'])
def test_endpoint():
    """
    Simple test endpoint to verify server is running
    """
    return jsonify({
        "success": True,
        "message": "Server is running",
        "endpoints": {
            "POST /api/upload_frame": "Upload image for barcode detection",
            "GET /result": "Get last detected barcode",
            "POST /debug": "Debug image upload",
            "GET /test": "This test endpoint"
        }
    }), 200

if __name__ == '__main__':
    print("Starting Barcode Reader Server...")
    print("Using OpenCV barcode detector")
    print("Available endpoints:")
    print("  POST /api/upload_frame - Upload image frame for barcode detection")
    print("  POST /debug - Debug image upload")
    print("  GET  /result - Get the last detected barcode")
    print("  GET  /test - Test endpoint")
    app.run(host='0.0.0.0', port=5000, debug=False)