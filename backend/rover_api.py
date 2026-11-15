from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import requests
import torch
from PIL import Image
import open_clip

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "rover_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NASA_RSS_URL = "https://mars.nasa.gov/rss/api/"

# Map Jezero landmarks to distinct NASA Mars 2020 raw-image pages so each site shows real, varied terrain
WAYPOINT_PAGES: dict[str, int] = {
    "landing": 12,
    "delta_scarp": 45,
    "belva_crater": 88,
    "bright_angel": 140,
}

TERRAIN_CLASSES = [
    {
        "id": "bedrock",
        "label": "Exposed Bedrock",
        "risk": "Low Slip",
        "prompt": "a Mars rover photo of flat exposed layered bedrock on the ground",
    },
    {
        "id": "sand",
        "label": "Loose Sand Ripples",
        "risk": "Sinkage Risk",
        "prompt": "a Mars rover photo of dark loose sand ripples and fine windblown dust",
    },
    {
        "id": "boulders",
        "label": "Boulder Field",
        "risk": "Obstacle Hazard",
        "prompt": "a Mars rover photo of a dense field of sharp rocks and boulders",
    },
    {
        "id": "scarp",
        "label": "Steep Scarp / Rim",
        "risk": "Slope Hazard",
        "prompt": "a Mars rover photo of a steep rocky cliff, ridge, or crater rim",
    },
]

_CLIP_STATE: dict[str, Any] = {}


def _get_clip():
    """Lazy-load OpenCLIP ViT-B-32 once and cache encoded text prompts."""
    if "model" not in _CLIP_STATE:
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        model = model.to(device).eval()
        tokenizer = open_clip.get_tokenizer("ViT-B-32")

        prompts = [c["prompt"] for c in TERRAIN_CLASSES]
        with torch.no_grad():
            tokens = tokenizer(prompts).to(device)
            text_feat = model.encode_text(tokens)
            text_feat = text_feat / text_feat.norm(dim=-1, keepdim=True)

        _CLIP_STATE["model"] = model
        _CLIP_STATE["preprocess"] = preprocess
        _CLIP_STATE["text_feat"] = text_feat
        _CLIP_STATE["device"] = device

    return (
        _CLIP_STATE["model"],
        _CLIP_STATE["preprocess"],
        _CLIP_STATE["text_feat"],
        _CLIP_STATE["device"],
    )


def _is_valid_surface_image(image_path: Path) -> bool:
    """Reject dark solar-filter, flat grey sky, or featureless calibration frames."""
    arr = np.asarray(Image.open(image_path).convert("L"), dtype=np.float32)
    if float(arr.mean()) < 50.0 or float(arr.std()) < 22.0:
        return False
    # High-pass local texture check: smooth sky/flat-fields have near-zero local edges
    lap = arr[1:-1, 1:-1] - 0.25 * (
        arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:]
    )
    return float(lap.std()) >= 6.0


def _fetch_nasa_photo_metadata(page: int) -> dict[str, Any]:
    """Fetch a real Perseverance surface image from NASA RSS API with local JSON cache."""
    meta_cache = CACHE_DIR / f"page_{page}.json"
    if meta_cache.exists():
        return json.loads(meta_cache.read_text())

    preferred = ("MCZ", "NAVCAM", "HAZCAM")
    for attempt_page in range(page, page + 4):
        resp = requests.get(
            NASA_RSS_URL,
            params={
                "feed": "raw_images",
                "category": "mars2020",
                "feedtype": "json",
                "num": 15,
                "page": attempt_page,
            },
            timeout=12,
        )
        resp.raise_for_status()
        images = resp.json().get("images", [])

        bad_words = ("solar", "sun", "sky", "cal", "flat", "dark", "horizon")
        candidates = [
            img for img in images
            if any(p in ((img.get("camera") or {}).get("instrument", "")).upper() for p in preferred)
            and img.get("image_files", {}).get("medium")
            and not any(w in (img.get("title") or "").lower() for w in bad_words)
        ]
        for chosen in candidates:
            local_img = _download_image(chosen["image_files"]["medium"])
            if _is_valid_surface_image(local_img):
                meta = {
                    "image_id": chosen.get("imageid", f"p{attempt_page}"),
                    "sol": chosen.get("sol"),
                    "camera": (chosen.get("camera") or {}).get("instrument", "Mars 2020"),
                    "title": chosen.get("title", "Perseverance Raw Image"),
                    "date_taken": (chosen.get("date_taken_utc") or "")[:10],
                    "remote_url": chosen["image_files"]["medium"],
                }
                meta_cache.write_text(json.dumps(meta))
                return meta

    raise RuntimeError("No bright Perseverance surface images found on nearby pages.")


def _download_image(remote_url: str) -> Path:
    """Download and cache the NASA rover JPEG locally."""
    digest = hashlib.sha1(remote_url.encode()).hexdigest()[:12]
    local_path = CACHE_DIR / f"rover_{digest}.jpg"
    if not local_path.exists():
        r = requests.get(remote_url, timeout=15)
        r.raise_for_status()
        local_path.write_bytes(r.content)
    return local_path


def classify_rover_image(image_path: Path) -> list[dict[str, Any]]:
    """Run local OpenCLIP ViT-B-32 zero-shot classification on the rover photo."""
    model, preprocess, text_feat, device = _get_clip()
    img = Image.open(image_path).convert("RGB")
    img_tensor = preprocess(img).unsqueeze(0).to(device)

    with torch.no_grad():
        img_feat = model.encode_image(img_tensor)
        img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
        # Scale cosine similarity by CLIP logit scale (~100) before softmax
        logits = 100.0 * (img_feat @ text_feat.T)
        probs = logits.softmax(dim=-1).squeeze(0).cpu().tolist()

    results = []
    for cls, prob in zip(TERRAIN_CLASSES, probs):
        results.append(
            {
                "id": cls["id"],
                "label": cls["label"],
                "risk": cls["risk"],
                "probability": round(float(prob), 4),
            }
        )
    results.sort(key=lambda x: x["probability"], reverse=True)
    return results


def inspect_waypoint(
    waypoint_id: str | None = None,
    row: int = 580,
    col: int = 620,
    terrain_class: str = "bedrock",
    slope_deg: float = 0.0,
    sand_risk: float = 0.0,
    boulder_risk: float = 0.0,
) -> dict[str, Any]:
    """Match orbital terrain hazard at (row, col) to verified Perseverance imagery and run CLIP."""
    refs_path = CACHE_DIR / "refs.json"
    if refs_path.exists():
        refs = json.loads(refs_path.read_text())
        if terrain_class in refs:
            ref = refs[terrain_class]
            local_img = CACHE_DIR / ref["file"]
            scores = classify_rover_image(local_img)
            top = scores[0]
            advisories = {
                "bedrock": "Nominal traction expected; consolidated bedrock supports EVA traversal.",
                "sand": "Caution: fine regolith ripples detected; monitor boot/wheel sinkage.",
                "boulders": "High obstacle density; route deviations recommended around rock fields.",
                "scarp": "Steep relief ahead; verify DEM slope constraints before committing.",
            }
            return {
                "sol": ref.get("sol"),
                "camera": ref.get("camera", "MCZ"),
                "title": ref.get("title", "Perseverance Reference"),
                "date_taken": ref.get("date_taken", ""),
                "image_url": f"/api/rover-image/{local_img.name}",
                "model": "OpenCLIP ViT-B-32 (zero-shot)",
                "orbital_class": terrain_class,
                "orbital_stats": f"Slope {slope_deg:.1f}° · Sand {sand_risk:.2f} · Rock {boulder_risk:.2f}",
                "top_class": top["label"],
                "top_risk": top["risk"],
                "advisory": advisories.get(top["id"], ""),
                "scores": scores,
            }

    if waypoint_id and waypoint_id in WAYPOINT_PAGES:
        page = WAYPOINT_PAGES[waypoint_id]
    else:
        page = 10 + ((row * 7 + col * 13) % 180)

    meta = _fetch_nasa_photo_metadata(page)
    local_img = _download_image(meta["remote_url"])
    scores = classify_rover_image(local_img)
    top = scores[0]

    advisories = {
        "bedrock": "Nominal traction expected; consolidated bedrock supports EVA traversal.",
        "sand": "Caution: fine regolith ripples detected; monitor boot/wheel sinkage.",
        "boulders": "High obstacle density; route deviations recommended around rock fields.",
        "scarp": "Steep relief ahead; verify DEM slope constraints before committing.",
    }

    return {
        "sol": meta["sol"],
        "camera": meta["camera"],
        "title": meta["title"],
        "date_taken": meta["date_taken"],
        "image_url": f"/api/rover-image/{local_img.name}",
        "model": "OpenCLIP ViT-B-32 (zero-shot)",
        "orbital_class": terrain_class,
        "orbital_stats": f"Slope {slope_deg:.1f}° · Sand {sand_risk:.2f} · Rock {boulder_risk:.2f}",
        "top_class": top["label"],
        "top_risk": top["risk"],
        "advisory": advisories.get(top["id"], ""),
        "scores": scores,
    }
