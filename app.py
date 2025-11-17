# app_pyzbar.py - Alternative using pyzbar
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
import time
import io
from pyzbar.pyzbar import decode

app = Flask(__name__)
CORS(app)

# Globals for barcode decoding
last_processed_barcode = None
last_processed_time = 0
processing_cooldown = 5  # seconds

@app.route('/api/upload_frame', methods=['POST'])
def handle_frame_upload():
    """
    Input endpoint: Accepts image frames and detects barcodes using pyzbar
    """
    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image data"}), 400

        print(f"Received image data: {len(img_data)} bytes")
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(img_data))
        print(f"Image size: {image.size}, mode: {image.mode}")
        
        # Detect barcodes
        barcodes = decode(image)
        print(f"Found {len(barcodes)} barcodes")
        
        for barcode in barcodes:
            print(f"Barcode: {barcode}")
        
        if barcodes:
            barcode_data = barcodes[0].data.decode('utf-8').strip()
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
            
        return jsonify({"success": False, "message": "No barcode detected"}), 200

    except Exception as e:
        print(f"Error in /api/upload_frame: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


def preprocess_image(frame):
    """
    Preprocess image to improve barcode detection
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Apply different preprocessing techniques
    processed_images = []
    
    # 1. Original grayscale
    processed_images.append(gray)
    
    # 2. Adaptive threshold
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
    processed_images.append(thresh)
    
    # 3. Gaussian blur + threshold
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh2 = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    processed_images.append(thresh2)
    
    # 4. Edge detection
    edges = cv2.Canny(gray, 50, 150)
    processed_images.append(edges)
    
    return processed_images

def detect_barcodes_enhanced(frame):
    """
    Enhanced barcode detection with multiple preprocessing techniques
    """
    best_barcode = None
    processed_images = preprocess_image(frame)
    
    for i, processed_img in enumerate(processed_images):
        try:
            result = barcode_detector.detectAndDecode(processed_img)
            print(f"Attempt {i+1} - OpenCV returned {len(result)} values")
            
            # Handle different return formats
            if len(result) == 4:
                ok, decoded_info, decoded_type, corners = result
            elif len(result) == 3:
                ok, decoded_info, corners = result
            else:
                continue
            
            if ok and decoded_info and len(decoded_info) > 0:
                barcode_data = decoded_info[0].strip()
                if barcode_data:
                    print(f"Found barcode with method {i+1}: {barcode_data}")
                    return True, [barcode_data]
                    
        except Exception as e:
            print(f"Method {i+1} failed: {e}")
            continue
    
    return False, []


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