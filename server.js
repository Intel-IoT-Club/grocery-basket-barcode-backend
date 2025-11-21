// Set up modules with correct ES Module syntax
import express from 'express';
// --- FIX 2: Use star import for QuaggaJS to handle its ES Module structure ---
import * as Quagga from 'quagga';
import Jimp from 'jimp';

const app = express();
const PORT = process.env.PORT || 5000; 

// --- Global State and Cooldown ---
let latestBarcodeResult = {
    data: "No barcode scanned yet.",
    timestamp: new Date().toISOString()
};
let lastScanTime = 0;
const COOLDOWN_SECONDS = 3;

// Configure Express to accept raw binary data (JPEG image buffer)
// ESP32-CAM will POST binary image data with Content-Type: image/jpeg
app.use(express.raw({ 
    type: 'image/jpeg', 
    limit: '10mb' 
})); 

// --- Core Barcode Decoding Function ---
async function decodeBarcode(imageBuffer) {
    try {
        // 1. Read the explicit Buffer into Jimp
        const image = await Jimp.read(imageBuffer);
        
        // 2. Convert to grayscale buffer required by Quagga
        // Note: QuaggaJS primarily focuses on 1D barcodes and requires grayscale data.
        const { data, width, height } = image.grayscale().bitmap;
        
        return new Promise((resolve, reject) => {
            // Quagga configuration
            Quagga.decodeSingle({
                src: data,
                numOfWorkers: 0, // Must be 0 for node-mode (server-side)
                inputStream: {
                    size: width,
                    height: height
                },
                decoder: {
                    readers: ["code_128_reader", "ean_reader", "upc_reader", "code_39_reader", "qr_code_reader"] 
                    // Added qr_code_reader for completeness, but Quagga excels at 1D codes.
                }
            }, (result) => {
                if (result && result.code) {
                    resolve(result.code);
                } else {
                    resolve(null);
                }
            });
        });
    } catch (error) {
        // Log Jimp/Quagga processing errors but don't crash the server
        console.error("Decoding failed during image processing:", error.message);
        return null;
    }
}


// --- API Endpoint to Receive Frame from ESP32-CAM ---
app.post('/api/upload_frame', async (req, res) => {
    const current_time = Date.now() / 1000;
    
    // Apply Cooldown check
    if (current_time - lastScanTime < COOLDOWN_SECONDS) {
        console.log("Scan ignored (cooldown active).");
        return res.status(202).json({ success: false, message: "Scan ignored (cooldown active)." });
    }

    if (!req.body || req.body.length === 0) {
        return res.status(400).json({ success: false, message: "No image data received" });
    }

    try {
        // --- FIX 1: Explicitly convert raw data to a standard Buffer for Jimp ---
        const imageBuffer = Buffer.from(req.body); 
        
        const decodedData = await decodeBarcode(imageBuffer);
        
        if (decodedData) {
            // Update global result
            latestBarcodeResult = {
                data: decodedData,
                timestamp: new Date().toISOString()
            };
            lastScanTime = current_time;
            console.log(`Barcode Decoded: ${decodedData}`);
            
            return res.json({ success: true, message: "Barcode detected and decoded.", data: decodedData });
        } else {
            return res.json({ success: false, message: "No barcode detected in frame." });
        }

    } catch (error) {
        // Log the error and return a 500 status
        console.error("Error in /api/upload_frame:", error);
        return res.status(500).json({ success: false, message: error.message });
    }
});

// --- API Endpoint to Display Result ---
app.get('/result', (req, res) => {
    res.json(latestBarcodeResult);
});

// Start the server
app.listen(PORT, () => {
    console.log(`Node.js Barcode Server running on port ${PORT}`);
});