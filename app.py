import cv2
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
import math

app = Flask(__name__)
CORS(app)

last_result = {"barcode": None, "method": None}

# OpenCV detector (fast)
detector = cv2.barcode_BarcodeDetector()

# -------------------------
# EAN-13 / UPC-A decoding tables
# -------------------------
L_CODE = {
    "0001101":"0","0011001":"1","0010011":"2","0111101":"3","0100011":"4",
    "0110001":"5","0101111":"6","0111011":"7","0110111":"8","0001011":"9"
}
G_CODE = {
    "0100111":"0","0110011":"1","0011011":"2","0100001":"3","0011101":"4",
    "0111001":"5","0000101":"6","0010001":"7","0001001":"8","0010111":"9"
}
R_CODE = {
    "1110010":"0","1100110":"1","1101100":"2","1000010":"3","1011100":"4",
    "1001110":"5","1010000":"6","1000100":"7","1001000":"8","1110100":"9"
}
# Parity patterns to leading digit map
PARITY_MAP = {
    "LLLLLL":"0","LLGLGG":"1","LLGGLG":"2","LLGGGL":"3","LGLLGG":"4",
    "LGGLLG":"5","LGGGLL":"6","LGLGLG":"7","LGLGGL":"8","LGGLGL":"9"
}

# -------------------------
# Utilities
# -------------------------
def enhance_img(img):
    # resize a bit to increase effective resolution
    h, w = img.shape[:2]
    scale = 1.5 if max(h,w) < 800 else 1.0
    if scale != 1.0:
        img = cv2.resize(img, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # denoise + sharpen
    gray = cv2.fastNlMeansDenoising(gray, h=7)
    kernel = np.array([[0, -1, 0],[-1, 5, -1],[0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)
    return gray

def find_barcode_roi(gray):
    # gradient (Sobel) to emphasize vertical bars
    gradX = cv2.Sobel(gray, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=3)
    gradX = cv2.convertScaleAbs(gradX)
    # blur + threshold
    blur = cv2.GaussianBlur(gradX, (9,9), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25,5))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    # find contours with large aspect ratio
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    candidates = []
    for cnt in contours:
        x,y,ww,hh = cv2.boundingRect(cnt)
        area = ww*hh
        if area < 500: 
            continue
        ar = ww/float(hh) if hh>0 else 0
        # barcode should be wide and not extremely tall
        if ar > 2.5 and ww > w*0.3:
            candidates.append((area, x,y,ww,hh))
    if not candidates:
        return None
    # choose largest by area
    candidates.sort(reverse=True)
    _, x,y,ww,hh = candidates[0]
    # expand slightly
    pad_w = int(ww*0.12)
    pad_h = int(hh*0.25)
    x0 = max(0, x-pad_w)
    y0 = max(0, y-pad_h)
    x1 = min(w, x+ww+pad_w)
    y1 = min(h, y+hh+pad_h)
    return (x0,y0,x1,y1)

def sample_stripe(img):
    # choose center horizontal stripe across barcode ROI
    h, w = img.shape[:2]
    cy = h // 2
    stripe_h = max(3, int(h * 0.12))  # 12% height stripe
    y0 = max(0, cy - stripe_h//2)
    y1 = min(h, cy + stripe_h//2)
    stripe = img[y0:y1, :]
    # collapse vertically
    profile = np.mean(stripe, axis=0)  # brightness per column
    return profile

def profile_to_binary(profile):
    # smooth profile
    kernel = np.ones(9)/9
    prof_s = np.convolve(profile, kernel, mode='same')
    # invert so dark bars -> high
    prof_s = 255 - prof_s
    # adaptive threshold using mean
    thr = np.mean(prof_s) * 0.7
    binary = (prof_s > thr).astype(np.uint8)
    return binary

def run_lengths(binary):
    # binary is 0/1 array; compute run lengths starting with first value
    vals = binary.tolist()
    if len(vals) == 0:
        return []
    runs = []
    cur = vals[0]
    count = 1
    for v in vals[1:]:
        if v == cur:
            count += 1
        else:
            runs.append((cur, count))
            cur = v
            count = 1
    runs.append((cur, count))
    return runs

def normalize_runs_to_modules(runs):
    # For EAN-13 we need total of 95 modules (bits)
    total_pixels = sum(r for _,r in runs)
    if total_pixels <= 0:
        return None
    unit = total_pixels / 95.0
    # convert run lengths to module counts
    modules = [max(1, int(round(r / unit))) for _, r in runs]
    # flatten to bits (starting with runs[0] value)
    bits = []
    color = runs[0][0] if runs else 0
    for m in modules:
        bits.extend([str(int(color))]*m)
        color = 1-color
    # adjust length by trimming/padding to 95
    if len(bits) < 95:
        # pad with last color (unlikely)
        bits.extend(bits[-1:] * (95 - len(bits)))
    elif len(bits) > 95:
        # try to trim symmetrically
        excess = len(bits) - 95
        # try trimming small alternating noise: remove from runs that are single modules
        bits = bits[:95]
    return ''.join(bits[:95])

def bits_to_digits(bits95):
    # verify guard patterns: left 3 bits 101, center 01010 at 45..49?, right 3 bits 101
    if len(bits95) != 95:
        return None
    # guard patterns positions
    left_guard = bits95[0:3]
    center_guard = bits95[45:50]
    right_guard = bits95[92:95]
    if left_guard != '101' or center_guard != '01010' or right_guard != '101':
        # not matching, but continue attempt
        pass
    # split into left(6*7) and right(6*7)
    left_bits = bits95[3:45]
    right_bits = bits95[50:92]
    # decode left 6 digits (each 7 bits) with possible L or G parity
    left_digits = []
    left_parity = []
    for i in range(6):
        chunk = left_bits[i*7:(i+1)*7]
        if chunk in L_CODE:
            left_digits.append(L_CODE[chunk])
            left_parity.append('L')
        elif chunk in G_CODE:
            left_digits.append(G_CODE[chunk])
            left_parity.append('G')
        else:
            return None
    # decode right 6 digits (R code)
    right_digits = []
    for i in range(6):
        chunk = right_bits[i*7:(i+1)*7]
        if chunk in R_CODE:
            right_digits.append(R_CODE[chunk])
        else:
            return None
    # determine first digit from parity
    parity_str = ''.join(left_parity)
    first_digit = None
    for k,v in PARITY_MAP.items():
        if k == parity_str:
            first_digit = v
            break
    if first_digit is None:
        # fallback: try to infer first digit 0
        first_digit = '0'
    digits = first_digit + ''.join(left_digits) + ''.join(right_digits)
    # EAN-13 check digit validation
    if len(digits) == 13:
        if not validate_ean13(digits):
            # try UPC-A (12 digits) by dropping first digit if possible
            pass
    return digits

def validate_ean13(code):
    # code is string of 13 digits
    if len(code) != 13 or not code.isdigit():
        return False
    s = 0
    for i, ch in enumerate(code[:12]):
        d = int(ch)
        if (i % 2) == 0:
            s += d
        else:
            s += 3*d
    check = (10 - (s % 10)) % 10
    return check == int(code[12])

# -------------------------
# Core custom decoder
# -------------------------
def custom_ean_decode(frame):
    gray = enhance_img(frame)
    roi = find_barcode_roi(gray)
    if roi is None:
        # fallback to center crop
        h,w = gray.shape
        roi = (int(w*0.05), int(h*0.35), int(w*0.95), int(h*0.65))
    x0,y0,x1,y1 = roi
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    # convert and denoise
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # try detect first using OpenCV on ROI (faster)
    try:
        res = detector.detectAndDecode(crop_gray)
        if len(res) == 4:
            ok, decoded_info, _, _ = res
        else:
            decoded_info, _, _ = res
            ok = decoded_info is not None and len(decoded_info) > 0
        if ok and decoded_info and len(decoded_info[0]) >= 11:
            return decoded_info[0]
    except Exception:
        pass

    # sample profile and try run-length decode
    profile = sample_stripe(crop_gray)
    binary = profile_to_binary(profile)
    runs = run_lengths(binary)
    if not runs or len(runs) < 20:
        return None
    modules_bits = normalize_runs_to_modules(runs)
    if not modules_bits:
        return None
    digits = bits_to_digits(modules_bits)
    if digits and validate_ean13(digits):
        return digits
    # final attempts: try trimming/padding small amounts and re-validate
    # attempt small shifts to align to 95 modules by shifting the binary profile
    for shift in range(-4,5):
        prof_shifted = np.roll(profile, shift)
        binary_s = profile_to_binary(prof_shifted)
        runs_s = run_lengths(binary_s)
        modules_bits_s = normalize_runs_to_modules(runs_s) if runs_s else None
        if modules_bits_s:
            digits_s = bits_to_digits(modules_bits_s)
            if digits_s and validate_ean13(digits_s):
                return digits_s
    return None

# -------------------------
# Flask endpoints
# -------------------------
@app.route('/api/upload_frame', methods=['POST'])
def upload_frame():
    global last_result
    try:
        data = request.data
        if not data:
            return jsonify({"success": False, "message": "No image"}), 400
        arr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"success": False, "message": "Invalid image"}), 400

        # 1) Try OpenCV global detector first
        try:
            res = detector.detectAndDecode(frame)
            if len(res) == 4:
                ok, decoded_info, decoded_type, _ = res
            else:
                decoded_info, decoded_type, _ = res
                ok = decoded_info is not None and len(decoded_info) > 0
            if ok and decoded_info and len(decoded_info[0]) >= 11:
                last_result = {"barcode": decoded_info[0], "method": "opencv"}
                return jsonify({"success": True, "barcode": decoded_info[0], "method": "opencv"}), 200
        except Exception:
            pass

        # 2) Try custom EAN-13 optimizer/decoder
        decoded = custom_ean_decode(frame)
        if decoded:
            last_result = {"barcode": decoded, "method": "custom"}
            return jsonify({"success": True, "barcode": decoded, "method": "custom"}), 200

        last_result = {"barcode": None, "method": None}
        return jsonify({"success": False, "message": "No barcode detected"}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/result', methods=['GET'])
def result():
    return jsonify(last_result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
