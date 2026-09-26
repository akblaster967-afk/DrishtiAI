from pathlib import Path
import sys
import tempfile
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from app.services.face_matcher import compare_document_and_capture


def main():


    face = cv2.imread(str(ROOT.parent / "src" / "assets" / "hero.png"))
    if face is None:


        face = np.full((480, 360, 3), 255, dtype=np.uint8)
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.png"
        b = Path(td) / "b.png"
        cv2.imwrite(str(a), face)
        transformed = cv2.convertScaleAbs(face, alpha=0.92, beta=8)
        cv2.imwrite(str(b), transformed)


        result = compare_document_and_capture(a, b)
        assert "status" in result and "score" in result
    print("face matcher smoke test: PASS")


if __name__ == "__main__":
    main()


def test_document_portrait_detection_does_not_require_eye_landmarks(monkeypatch):
    import app.services.face_matcher as fm

    image = np.zeros((500, 700, 3), dtype=np.uint8)
    image[:] = 220

    rng = np.random.default_rng(7)
    image[120:390, 70:300] = rng.integers(70, 190, size=(270, 230, 3), dtype=np.uint8)

    monkeypatch.setattr(
        fm,
        "_simple_face_candidates",
        lambda img, require_eye=False: [(85, 135, 125, 150)],
    )
    monkeypatch.setattr(fm, "_eye_center_pair", lambda gray: None)

    for doc_type in ("PAN", "AADHAAR", "PASSPORT", "DRIVING_LICENSE", "COLLEGE_ID", "NATIONAL_ID", "VISA"):
        candidates = fm._document_face_candidates(image, doc_type)
        assert candidates, doc_type


def test_pan_portrait_region_outranks_identifier_like_false_positive(monkeypatch):
    import app.services.face_matcher as fm
    image = np.full((1010, 1500, 3), 180, dtype=np.uint8)
    rng = np.random.default_rng(11)
    image[280:520, 40:330] = rng.integers(60, 220, size=(240, 290, 3), dtype=np.uint8)
    image[280:520, 800:1020] = rng.integers(60, 220, size=(240, 220, 3), dtype=np.uint8)


    candidates = [
        (850, 330, 150, 150),
        (105, 345, 147, 147),
        (8, 812, 120, 120),
    ]
    monkeypatch.setattr(fm, "_simple_face_candidates", lambda img, require_eye=False: list(candidates))
    monkeypatch.setattr(fm, "_ocr_text_boxes", lambda img: [])
    monkeypatch.setattr(fm, "_eye_center_pair", lambda gray: None)
    monkeypatch.setattr(fm, "_face_shape_score", lambda crop: 0.55)
    got = fm._document_face_candidates(image, "PAN")
    assert got
    assert got[0] == (105, 345, 147, 147)


def test_final_document_face_selection_prefers_eye_supported_portrait(monkeypatch):
    import app.services.face_matcher as fm

    image = np.full((600, 900, 3), 150, dtype=np.uint8)
    candidates = [(650, 180, 140, 140), (90, 180, 140, 140)]
    monkeypatch.setattr(fm, "_document_face_candidates", lambda img, document_type=None: list(candidates))
    monkeypatch.setattr(fm, "_template_face_candidates", lambda img, document_type=None: [])
    monkeypatch.setattr(fm, "_eye_center_pair", lambda crop: ((35, 45), (100, 45)) if crop.shape[1] < 500 else None)

    _, box, _ = fm._best_oriented_face(image, "PAN")

    assert box == (90, 180, 140, 140)


def test_document_face_layouts_cover_all_supported_families():
    import app.services.face_matcher as fm
    supported = {
        "PAN", "AADHAAR", "PASSPORT", "DRIVING_LICENSE", "COLLEGE_ID",
        "NATIONAL_ID", "VISA",
    }
    assert supported.issubset(set(fm.DOCUMENT_FACE_LAYOUTS))
    for doc_type in supported:
        layout = fm.DOCUMENT_FACE_LAYOUTS[doc_type]
        assert layout["preferred"]
        assert layout["fallback"]
