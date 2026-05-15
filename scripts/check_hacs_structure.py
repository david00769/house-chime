"""Validate the House Chime HACS repository shape."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
DOMAIN = "house_chime"


def main() -> None:
    errors: list[str] = []

    integration_dirs = sorted(path for path in CUSTOM_COMPONENTS.iterdir() if path.is_dir())
    if [path.name for path in integration_dirs] != [DOMAIN]:
        errors.append(
            "custom_components must contain exactly one integration directory: "
            f"{DOMAIN}"
        )

    integration_dir = CUSTOM_COMPONENTS / DOMAIN
    manifest_path = integration_dir / "manifest.json"
    hacs_path = ROOT / "hacs.json"
    brand_icon_path = integration_dir / "brand" / "icon.png"

    for required_path in (
        integration_dir / "__init__.py",
        manifest_path,
        hacs_path,
        brand_icon_path,
        ROOT / "README.md",
    ):
        if not required_path.exists():
            errors.append(f"missing_required_file:{required_path.relative_to(ROOT)}")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for key in (
            "domain",
            "documentation",
            "issue_tracker",
            "codeowners",
            "name",
            "version",
            "config_flow",
            "integration_type",
        ):
            if key not in manifest:
                errors.append(f"manifest_missing_key:{key}")
        if manifest.get("domain") != DOMAIN:
            errors.append(f"manifest_domain_mismatch:{manifest.get('domain')}")
        if not manifest.get("codeowners"):
            errors.append("manifest_codeowners_empty")
        if manifest.get("name") != "House Chime":
            errors.append(f"manifest_name_mismatch:{manifest.get('name')}")

    if hacs_path.exists():
        hacs = json.loads(hacs_path.read_text())
        if not hacs.get("name"):
            errors.append("hacs_json_missing_name")

    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()

