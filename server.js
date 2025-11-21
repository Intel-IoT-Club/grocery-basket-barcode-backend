import express from 'express';
import Jimp from 'jimp';

// --- Robust Import Strategy for Quagga ---
import QuaggaPkg from 'quagga';
const Quagga = QuaggaPkg.default || QuaggaPkg; 
// -----------------------------------------

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
app.use(express.raw({ 
    type: 'image/jpeg', 
    limit: '10mb' 
})); 

// --- Core Barcode Decoding Function ---
async function decodeBarcode(imageBuffer) {
    try {
        // 1. Read the explicit Buffer into Jimp
        const image = await Jimp.read(imageBuffer);
        
        // 2. Convert image to Base64 Data URI
        // This fixes the "Invalid file type" error by giving Quagga a standard format
        const base64Image = await image.getBase64Async(Jimp.MIME_JPEG);
        
        return new Promise((resolve, reject) => {
            if (typeof Quagga.decodeSingle !== 'function') {
                console.error("CRITICAL ERROR: Quagga.decodeSingle is not a function.");
                resolve(null);
                return;
            }

            Quagga.decodeSingle({
                src: base64Image, // Pass the Base64 string instead of raw pixels
                numOfWorkers: 0,  // Must be 0 for node-mode
                inputStream: {
                    size: 800     // Optional: restricts processing size for speed
                },
                decoder: {
                    // Add 'qr_code_reader' if you need QR codes, but Quagga is best for 1D
                    readers: ["code_128_reader", "ean_reader", "upc_reader", "code_39_reader"]
                }
            }, (result) => {
                if (result && result.codeResult) {
                    resolve(result.codeResult.code);
                } else {
                    resolve(null);
                }
            });
        });
    } catch (error) {
        console.error("Decoding failed during processing:", error.message);
        return null;
    }
}

// --- API Endpoint to Receive Frame from ESP32-CAM ---
app.post('/api/upload_frame', async (req, res) => {
    const current_time = Date.now() / 1000;
    
    // Apply Cooldown
    if (current_time - lastScanTime < COOLDOWN_SECONDS) {
        console.log("Scan ignored (cooldown active).");
        return res.status(202).json({ success: false, message: "Scan ignored (cooldown active)." });
    }

    if (!req.body || req.body.length === 0) {
        return res.status(400).json({ success: false, message: "No image data received" });
    }

    try {
        const imageBuffer = Buffer.from(req.body); 
        const decodedData = await decodeBarcode(imageBuffer);
        
        if (decodedData) {
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
        console.error("Error in /api/upload_frame:", error);
        return res.status(500).json({ success: false, message: error.message });
    }
});

// --- API Endpoint to Display Result ---
app.get('/result', (req, res) => {
    res.json(latestBarcodeResult);
});

app.listen(PORT, () => {
    console.log(`Node.js Barcode Server running on port ${PORT}`);
});