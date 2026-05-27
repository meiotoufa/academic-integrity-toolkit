"""academic_integrity_utils.py - Academic Integrity Toolkit"""
from __future__ import annotations
import json, math, re, statistics, time, os
import urllib.request, urllib.error, urllib.parse
import hashlib, collections
from pathlib import Path

_CROSSREF_BASE = "https://api.crossref.org"
_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_POLITE_MAILTO = ""

def _http_get(url, timeout=15):
    ua = "AcademicIntegrityChecker/1.0"
    if _POLITE_MAILTO: ua += f" (mailto:{_POLITE_MAILTO})"
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def verify_doi(doi):
    """Verify DOI via CrossRef."""
    doi = doi.strip()
    encoded = urllib.parse.quote(doi, safe="")
    url = _CROSSREF_BASE + "/works/" + encoded
    data = _http_get(url)
    if data and "message" in data:
        msg = data["message"]
        pub = msg.get("published-print") or msg.get("published-online") or msg.get("created", {})
        year = pub.get("date-parts", [[None]])[0][0]
        auths = []
        for a in msg.get("author", []):
            auths.append(a.get("given", "") + " " + a.get("family", ""))
        return {"exists": True, "title": msg.get("title", [""])[0],
                "authors": auths, "year": year,
                "journal": msg.get("container-title", [""])[0], "doi": doi}
    return {"exists": False, "doi": doi}

def search_crossref(title, top_k=3):
    query = urllib.parse.quote(title)
    url = _CROSSREF_BASE + "/works?query.title=" + query + "&rows=" + str(top_k)
    data = _http_get(url, timeout=20)
    if not data or "message" not in data: return []
    results = []
    for item in data["message"].get("items", []):
        auths = []
        for a in item.get("author", []):
            auths.append(a.get("given", "") + " " + a.get("family", ""))
        pub = item.get("published-print") or {}
        year = pub.get("date-parts", [[None]])[0][0]
        jrn = item.get("container-title", [""])[0] if item.get("container-title") else ""
        results.append({"title": item.get("title", [""])[0], "authors": auths,
                         "year": year, "journal": jrn, "doi": item.get("DOI", "")})
    return results

def search_semantic_scholar(title, top_k=3):
    query = urllib.parse.quote(title)
    url = _SS_BASE + "/paper/search?query=" + query + "&limit=" + str(top_k) + "&fields=title,authors,year,venue,externalIds"
    data = _http_get(url, timeout=15)
    if not data or "data" not in data: return []
    results = []
    for item in data["data"]:
        auths = [a.get("name", "") for a in item.get("authors", [])]
        ext = item.get("externalIds") or {}
        results.append({"title": item.get("title", ""), "authors": auths,
                         "year": item.get("year"), "venue": item.get("venue", ""),
                         "doi": ext.get("DOI", "")})
    return results

def _title_sim(a, b):
    if not a or not b: return 0.0
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb: return 0.0
    return len(wa & wb) / len(wa | wb)

def _author_overlap(ref_authors, found_authors):
    if not ref_authors or not found_authors: return False
    ref_lower = ref_authors.lower()
    for fa in found_authors:
        surname = fa.strip().split()[-1].lower() if fa.strip() else ""
        if surname and len(surname) > 2 and surname in ref_lower: return True
    return False

def verify_single_citation(ref, delay=0.5):
    """Verify one citation. ref: {title, authors, year, journal, doi}."""
    title = ref.get("title", "")
    authors = ref.get("authors", "")
    year = ref.get("year")
    doi = ref.get("doi", "")
    result = {"title": title, "status": "❌", "reason": "Not verified", "source": None}
    if doi:
        info = verify_doi(doi)
        if info["exists"]:
            result["status"] = "✅"
            result["reason"] = "DOI verified: " + info["title"][:60]
            result["source"] = "crossref_doi"
            if title and _title_sim(title, info["title"]) < 0.3:
                result["status"] = "⚠️"
                result["reason"] = "DOI exists but title mismatch"
            return result
        else:
            result["reason"] = "DOI does not resolve"
    time.sleep(delay)
    if title:
        cr = search_crossref(title, top_k=3)
        for c in cr:
            sim = _title_sim(title, c["title"])
            if sim >= 0.7:
                result["status"] = "✅"
                result["reason"] = "Title match (" + str(round(sim*100)) + "%) in CrossRef"
                result["source"] = "crossref_search"
                if year and c["year"] and abs(int(year) - int(c["year"])) > 1:
                    result["status"] = "⚠️"
                    result["reason"] += " (year mismatch)"
                return result
        time.sleep(delay)
        ss = search_semantic_scholar(title, top_k=3)
        for s in ss:
            sim = _title_sim(title, s["title"])
            if sim >= 0.7:
                result["status"] = "✅"
                result["reason"] = "Title match (" + str(round(sim*100)) + "%) in S2"
                result["source"] = "semantic_scholar"
                return result
        best_sim = 0
        for c in cr + ss:
            s = _title_sim(title, c["title"])
            if s > best_sim: best_sim = s
        if best_sim >= 0.4:
            result["status"] = "⚠️"
            result["reason"] = "Partial match (" + str(round(best_sim*100)) + "%)"
        else:
            result["status"] = "❌"
            result["reason"] = "No matching paper found"
    return result

def check_citations(refs, delay=0.8, progress=True):
    """Batch verify citations."""
    results = []
    for i, ref in enumerate(refs):
        if progress:
            t = ref.get("title", "?")[:60]
            print("  [" + str(i+1) + "/" + str(len(refs)) + "] " + t)
        r = verify_single_citation(ref, delay=delay)
        results.append(r)
    v = sum(1 for r in results if r["status"] == "✅")
    s = sum(1 for r in results if r["status"] == "⚠️")
    h = sum(1 for r in results if r["status"] == "❌")
    if progress:
        print("  Summary: v=" + str(v) + " s=" + str(s) + " h=" + str(h) + " / " + str(len(refs)))
    return results

# ====== Module 2: Data Anomaly Analysis ======

def benford_test(data, significance=0.05):
    """Benford first-digit test. Needs >=100 positive numbers."""
    digits = []
    for x in data:
        if x is None: continue
        x = abs(float(x))
        if x == 0: continue
        s = str(x).lstrip("0").lstrip(".").lstrip("0")
        if s and s[0].isdigit() and s[0] != "0":
            digits.append(int(s[0]))
    n = len(digits)
    if n < 30:
        return {"error": "Need >=30 data points", "n": n}
    observed = collections.Counter(digits)
    expected = {d: n * math.log10(1 + 1/d) for d in range(1, 10)}
    chi2 = sum((observed.get(d, 0) - expected[d])**2 / expected[d] for d in range(1, 10))
    # Chi2 with 8 dof approximate p-value
    # Using Wilson-Hilferty approximation
    k = 8  # degrees of freedom
    z = (chi2/k)**(1/3) - (1 - 2/(9*k))
    z = z / math.sqrt(2/(9*k))
    # Standard normal CDF approximation
    p_approx = 0.5 * (1 + math.erf(-z / math.sqrt(2)))
    p_approx = max(0.0001, min(1.0, p_approx))
    if p_approx < 0.01: verdict = "FAIL"
    elif p_approx < significance: verdict = "SUSPICIOUS"
    else: verdict = "PASS"
    obs_dict = {d: observed.get(d, 0) for d in range(1, 10)}
    exp_dict = {d: round(expected[d], 1) for d in range(1, 10)}
    return {"chi2": round(chi2, 2), "p_value": round(p_approx, 4),
            "observed": obs_dict, "expected": exp_dict, "n": n, "verdict": verdict}

def grim_test(mean, n, scale_min=1, scale_max=5, decimals=2):
    """GRIM test: check if reported mean is mathematically possible."""
    granularity = 1.0 / n
    total_min = n * scale_min
    total_max = n * scale_max
    precision = 10 ** (-decimals)
    for total in range(total_min, total_max + 1):
        computed_mean = total / n
        if abs(computed_mean - mean) < precision / 2:
            return {"possible": True, "mean": mean, "n": n,
                    "closest_possible": round(computed_mean, decimals + 1)}
    # Find nearest possible
    nearest = None
    min_diff = float("inf")
    for total in range(total_min, total_max + 1):
        cm = total / n
        diff = abs(cm - mean)
        if diff < min_diff:
            min_diff = diff
            nearest = round(cm, decimals + 1)
    return {"possible": False, "mean": mean, "n": n, "nearest_possible": nearest}

def detect_data_anomalies(data):
    """Detect anomalies: duplicates, last-digit distribution, precision."""
    if not data: return {"error": "empty data"}
    n = len(data)
    # Duplicate analysis
    counter = collections.Counter(data)
    dup_count = sum(v for v in counter.values() if v > 1)
    dup_ratio = dup_count / n if n else 0
    # Last digit distribution
    last_digits = []
    for x in data:
        s = str(x).rstrip("0").rstrip(".")
        if s and s[-1].isdigit():
            last_digits.append(int(s[-1]))
    ld_counter = collections.Counter(last_digits)
    expected_ld = len(last_digits) / 10 if last_digits else 1
    ld_chi2 = sum((ld_counter.get(d, 0) - expected_ld)**2 / max(expected_ld, 1) for d in range(10))
    # Precision analysis
    decimal_places = []
    for x in data:
        s = str(float(x))
        if "." in s:
            dp = len(s.split(".")[1].rstrip("0"))
        else:
            dp = 0
        decimal_places.append(dp)
    dp_counter = collections.Counter(decimal_places)
    precision_uniform = len(dp_counter) <= 2
    patterns = []
    if dup_ratio > 0.15: patterns.append("High duplicate ratio: " + str(round(dup_ratio*100)) + "%")
    if ld_chi2 > 16.92: patterns.append("Last digit non-uniform (chi2=" + str(round(ld_chi2, 1)) + ")")
    if not precision_uniform and len(dp_counter) > 3:
        patterns.append("Inconsistent decimal precision")
    return {"n": n, "duplicate_ratio": round(dup_ratio, 3),
            "last_digit_chi2": round(ld_chi2, 2),
            "precision_counts": dict(dp_counter),
            "suspicious_patterns": patterns,
            "verdict": "SUSPICIOUS" if patterns else "PASS"}

def p_value_analysis(p_values):
    """Check p-value distribution for suspicious patterns."""
    if not p_values: return {"error": "empty"}
    n = len(p_values)
    sig = sum(1 for p in p_values if p < 0.05)
    near = sum(1 for p in p_values if 0.01 <= p < 0.05)
    tiny = sum(1 for p in p_values if p < 0.001)
    sig_rate = sig / n
    flags = []
    if sig_rate > 0.9 and n >= 5: flags.append("Unrealistically high significance rate")
    if near > sig * 0.6 and sig >= 3: flags.append("Too many p-values clustered just below 0.05")
    return {"total": n, "significant": sig, "near_boundary": near,
            "very_small": tiny, "sig_rate": round(sig_rate, 3),
            "flags": flags, "verdict": "SUSPICIOUS" if flags else "PASS"}

# ====== Module 3: Image Fraud Detection ======

def _ensure_pil():
    try:
        from PIL import Image
        import numpy as np
        return Image, np
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "numpy", "-q"])
        from PIL import Image
        import numpy as np
        return Image, np

def ela_analysis(image_path, quality=90, scale=15):
    """Error Level Analysis for JPEG manipulation detection."""
    Image, np = _ensure_pil()
    import io
    orig = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    orig.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    recompressed = Image.open(buf).convert("RGB")
    orig_arr = np.array(orig, dtype=np.float32)
    recomp_arr = np.array(recompressed, dtype=np.float32)
    diff = np.abs(orig_arr - recomp_arr)
    ela_img = np.clip(diff * scale, 0, 255).astype(np.uint8)
    ela_pil = Image.fromarray(ela_img)
    # Analyze hotspots
    gray_diff = np.mean(diff, axis=2)
    mean_err = float(np.mean(gray_diff))
    max_err = float(np.max(gray_diff))
    std_err = float(np.std(gray_diff))
    # Find hotspot regions (blocks with high error)
    block = 32
    h, w = gray_diff.shape
    hotspots = []
    threshold = mean_err + 3 * std_err
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            block_mean = float(np.mean(gray_diff[y:y+block, x:x+block]))
            if block_mean > threshold:
                hotspots.append({"x": x, "y": y, "size": block, "level": round(block_mean, 1)})
    if max_err > mean_err * 5 and std_err > mean_err * 0.8:
        verdict = "SUSPICIOUS"
    else:
        verdict = "PASS"
    return {"ela_image": ela_pil, "mean_error": round(mean_err, 2),
            "max_error": round(max_err, 2), "std_error": round(std_err, 2),
            "hotspots": hotspots[:20], "verdict": verdict}

def check_image_metadata(image_path):
    """Check image EXIF/metadata for editing signs."""
    Image, np = _ensure_pil()
    from PIL.ExifTags import TAGS
    img = Image.open(image_path)
    info = {"format": img.format, "size": img.size, "mode": img.mode}
    flags = []
    exif_data = {}
    raw_exif = img.getexif() if hasattr(img, "getexif") else {}
    for tag_id, value in raw_exif.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        if isinstance(value, bytes): value = value[:50].hex()
        exif_data[tag_name] = str(value)[:200]
    software = exif_data.get("Software", "")
    if "photoshop" in software.lower(): flags.append("photoshop_edited")
    if "gimp" in software.lower(): flags.append("gimp_edited")
    if not exif_data: flags.append("metadata_stripped")
    # Check for XMP data in file
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
        if b"photoshop" in raw.lower(): flags.append("photoshop_in_binary")
        if b"adobe" in raw.lower(): flags.append("adobe_in_binary")
    except Exception: pass
    info["software"] = software
    info["exif"] = exif_data
    info["flags"] = list(set(flags))
    return info

def detect_clone_regions(image_path, block_size=16, threshold=0.95):
    """Detect copy-move (clone) regions using block hashing."""
    Image, np = _ensure_pil()
    img = Image.open(image_path).convert("L")
    arr = np.array(img, dtype=np.float32)
    h, w = arr.shape
    bs = block_size
    blocks = {}
    for y in range(0, h - bs, bs // 2):
        for x in range(0, w - bs, bs // 2):
            block = arr[y:y+bs, x:x+bs]
            # Normalize block
            bm = block.mean()
            bstd = block.std()
            if bstd < 1: continue  # skip flat regions
            norm = ((block - bm) / bstd * 100).astype(np.int8)
            key = hashlib.md5(norm.tobytes()).hexdigest()[:12]
            if key in blocks:
                ox, oy = blocks[key]
                dist = math.sqrt((x - ox)**2 + (y - oy)**2)
                if dist > bs * 2:  # Not overlapping
                    blocks[key + "_dup"] = (x, y)
            else:
                blocks[key] = (x, y)
    # Find duplicates
    clone_pairs = []
    seen = set()
    for key, pos in blocks.items():
        if "_dup" in key:
            orig_key = key.replace("_dup", "")
            if orig_key in blocks:
                p1 = blocks[orig_key]
                p2 = pos
                pair_key = str(sorted([p1, p2]))
                if pair_key not in seen:
                    seen.add(pair_key)
                    clone_pairs.append({
                        "region_a": {"x": p1[0], "y": p1[1], "size": bs},
                        "region_b": {"x": p2[0], "y": p2[1], "size": bs},
                        "similarity": 1.0})
    verdict = "SUSPICIOUS" if len(clone_pairs) > 3 else "PASS"
    return {"clone_pairs": clone_pairs[:50], "total_clones": len(clone_pairs),
            "verdict": verdict}

def compare_image_noise(path_a, path_b):
    """Compare noise patterns between two image panels."""
    Image, np = _ensure_pil()
    a = np.array(Image.open(path_a).convert("L"), dtype=np.float32)
    b = np.array(Image.open(path_b).convert("L"), dtype=np.float32)
    # Extract high-frequency noise via Laplacian-like filter
    def noise(img):
        kernel = np.array([[0,-1,0],[-1,4,-1],[0,-1,0]], dtype=np.float32)
        from scipy.signal import convolve2d
        return convolve2d(img, kernel, mode="same")
    try:
        na = noise(a)
        nb = noise(b)
        # Resize to same shape if needed
        min_h = min(na.shape[0], nb.shape[0])
        min_w = min(na.shape[1], nb.shape[1])
        na = na[:min_h, :min_w].flatten()
        nb = nb[:min_h, :min_w].flatten()
        corr = float(np.corrcoef(na, nb)[0, 1])
    except ImportError:
        # Fallback without scipy
        min_h = min(a.shape[0], b.shape[0])
        min_w = min(a.shape[1], b.shape[1])
        fa = a[:min_h, :min_w].flatten()
        fb = b[:min_h, :min_w].flatten()
        corr = float(np.corrcoef(fa, fb)[0, 1])
    verdict = "SUSPICIOUS" if abs(corr) > 0.8 else "PASS"
    return {"noise_correlation": round(corr, 4), "verdict": verdict}
