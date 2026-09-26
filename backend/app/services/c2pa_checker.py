from __future__ import annotations

import json
from pathlib import Path
from typing import Any



AI_CLAIM_GENERATORS = {
    "openai",
    "dall-e",
    "midjourney",
    "stable diffusion",
    "stability ai",
    "adobe firefly",
    "adobe express",
    "adobe photoshop",
    "gimp",
    "canva",
    "sora",
    "imagen",
    "google deepmind",
    "bing image creator",
    "ideogram",
    "leonardo ai",
}

AI_EDITING_ACTIONS = {
    "c2pa.created",
    "c2pa.edited",
    "c2pa.opened",
    "c2pa.placed",
    "c2pa.drawing",
}

VALIDATION_PASS_VALUES = {
    "",
    "VALID",
    "VALID_OK",
    "ALL_PASS",
    "PASS",
}


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_manifest_details(
    manifest_id: str,
    manifest: dict[str, Any],
    active_id: str | None,
) -> dict[str, Any]:
    claim_generator = str(manifest.get("claim_generator") or "").strip()
    claim_generator_info = manifest.get("claim_generator_info") or []
    generator_names: list[str] = []
    if claim_generator:
        generator_names.append(claim_generator)
    for info in claim_generator_info or []:
        if isinstance(info, dict):
            name = str(info.get("name") or "").strip()
            if name and name not in generator_names:
                generator_names.append(name)

    signature_info = manifest.get("signature_info") or {}
    signer_issuer = str(signature_info.get("issuer") or "").strip()
    signer_cn = str(signature_info.get("cn") or "").strip()
    signer = signer_issuer or signer_cn

    editing_history: list[dict[str, Any]] = []
    assertions = manifest.get("assertions") or {}
    actions = assertions.get("actions") or []
    digital_source_type = None
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        editing_history.append(
            {
                "action": str(action.get("action") or ""),
                "when": str(action.get("when") or ""),
                "softwareAgent": str(action.get("softwareAgent") or ""),
                "digitalSourceType": str(
                    (action.get("digitalSourceType") or {}).get("value") or ""
                ),
                "parameters": action.get("parameters") or [],
            }
        )
        dst = (action.get("digitalSourceType") or {}).get("value")
        if dst:
            digital_source_type = str(dst)

    digital_source_info = assertions.get("digitalSource")
    if isinstance(digital_source_info, dict):
        for item in digital_source_info.get("digitalSourceType") or []:
            if isinstance(item, dict) and item.get("value"):
                digital_source_type = str(item["value"])

    ingredients = manifest.get("ingredients") or []
    return {
        "manifestId": manifest_id,
        "active": manifest_id == active_id,
        "title": str(manifest.get("title") or ""),
        "claimGenerator": claim_generator,
        "claimGeneratorInfo": generator_names,
        "producer": str(manifest.get("producer") or ""),
        "issuerName": signer or None,
        "signatureInfo": signature_info,
        "ingredientCount": len(ingredients if isinstance(ingredients, list) else []),
        "editingHistory": editing_history,
        "digitalSourceType": digital_source_type,
    }


def check_c2pa(file_path: str | Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "has_c2pa": False,
        "issuer_name": None,
        "is_ai_generated_flag": False,
        "validation_status": "UNAVAILABLE",
        "claim_signers": [],
        "editing_history": [],
        "active_manifest_count": 0,
        "manifest_count": 0,
        "generators": [],
        "digital_source_type": None,
        "reason": None,
        "purpose": "PROVENANCE_CREDENTIAL",
    }

    try:
        from c2pa import Reader
    except Exception as import_error:
        result["reason"] = "c2pa-python is not installed; C2PA screening was skipped."
        return result

    try:
        reader = Reader.from_file(str(file_path))
        store_json = reader.json()
    except Exception as read_error:
        result["reason"] = f"C2PA manifest could not be read: {read_error}"
        result["validation_status"] = "NO_MANIFEST"
        return result

    try:
        store = json.loads(store_json)
    except Exception as parse_error:
        result["reason"] = f"C2PA store JSON could not be parsed: {parse_error}"
        return result

    result["available"] = True

    manifests = store.get("manifests") or {}
    active_manifest_id = store.get("active_manifest")
    if not manifests and not active_manifest_id:
        result["validation_status"] = "NO_MANIFEST"
        result["reason"] = "No C2PA manifest store is embedded in this image."
        return result

    result["has_c2pa"] = bool(manifests)
    result["validation_status"] = str(store.get("validation_status") or "NO_MANIFEST")

    active_count = 0
    claim_signers: list[str] = []
    editing_history: list[dict[str, Any]] = []
    generators: list[str] = []
    spec_versions: list[str] = []
    active_generator_hits: list[str] = []

    for manifest_id, manifest in manifests.items():
        if not isinstance(manifest, dict):
            continue
        details = _extract_manifest_details(manifest_id, manifest, active_manifest_id)
        if details["active"]:
            active_count += 1
        if details["issuerName"] and details["issuerName"] not in claim_signers:
            claim_signers.append(details["issuerName"])
        editing_history.extend(details["editingHistory"])
        for gen in details["claimGeneratorInfo"]:
            if gen and gen not in generators:
                generators.append(gen)
        spec = str(manifest.get("claim_version") or "").strip()
        if spec and spec not in spec_versions:
            spec_versions.append(spec)
        normalized_generator = _normalize(details["claimGenerator"] or details["claimGeneratorInfo"])
        if details["active"] and any(
            marker in normalized_generator for marker in AI_CLAIM_GENERATORS
        ):
            active_generator_hits.append(details["claimGenerator"])
        if (
            details["digitalSourceType"]
            and result["digital_source_type"] is None
        ):
            result["digital_source_type"] = details["digitalSourceType"]

    result["active_manifest_count"] = active_count
    result["manifest_count"] = len(manifests)
    result["claim_signers"] = claim_signers
    result["editing_history"] = editing_history
    result["generators"] = generators
    result["issuer_name"] = claim_signers[0] if claim_signers else None
    result["specVersions"] = spec_versions

    validation_status = str(result["validation_status"])
    is_signed = bool(claim_signers) and validation_status in (
        *VALIDATION_PASS_VALUES,
        "PARTIAL_PASS",
    )
    result["is_ai_generated_flag"] = bool(active_generator_hits) and is_signed

    return result
