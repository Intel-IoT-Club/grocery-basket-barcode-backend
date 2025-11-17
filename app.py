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
    Input endpoint: Accepts image frames and detects barcodes
    """
    try:
        img_data = request.data
        if not img_data:
            return jsonify({"success": False, "message": "No image data"}), 400

        # Convert to PIL Image
        image = Image.open(io.BytesIO(img_data))
        
        # Detect barcodes
        barcodes = decode(image)
        
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

if __name__ == '__main__':
    print("Starting Barcode Reader Server...")
    print("Available endpoints:")
    print("  POST /api/upload_frame - Upload image frame for barcode detection")
    print("  GET  /result - Get the last detected barcode")
    app.run(host='0.0.0.0', port=5000, debug=False)