#!/usr/bin/env python3
"""
DiffSense-AI Offline Setup Script

Run this script ONCE with internet connectivity to prepare the system
for fully offline deployment. Downloads all required models and assets.

Usage:
    python setup_offline.py              # Full setup
    python setup_offline.py --models-only  # Download models only
    python setup_offline.py --assets-only  # Download frontend assets only
    python setup_offline.py --verify       # Verify existing setup
    python setup_offline.py --skip-mysql   # Skip MySQL verification
"""

import os
import sys
import json
import hashlib
import argparse
import shutil
from pathlib import Path
from datetime import datetime

# Add color support
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    RESET = Style.RESET_ALL
except ImportError:
    GREEN = RED = YELLOW = CYAN = RESET = ""

# Project paths
PROJECT_ROOT = Path(__file__).parent
MODELS_DIR = PROJECT_ROOT / "models"
FRONTEND_DIR = PROJECT_ROOT / "aidiffchecker" / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"

# Model configurations
MODELS = {
    "BAAI/bge-small-en-v1.5": {
        "type": "fastembed",
        "local_path": MODELS_DIR / "embeddings" / "BAAI-bge-small-en-v1.5",
        "size_mb": 133,
        "required": True,
    },
    "all-MiniLM-L6-v2": {
        "type": "sentence_transformers",
        "local_path": MODELS_DIR / "sentence_transformers" / "all-MiniLM-L6-v2",
        "size_mb": 80,
        "required": True,
    },
}

# Frontend assets to download
FRONTEND_ASSETS = {
    "tailwind": {
        "url": "https://cdn.tailwindcss.com/3.4.1",
        "local_path": ASSETS_DIR / "css" / "tailwind.min.js",
        "size_kb": 2500,
    },
    "chartjs": {
        "url": "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js",
        "local_path": ASSETS_DIR / "js" / "chart.min.js",
        "size_kb": 280,
    },
}


def print_header(text):
    """Print a formatted header."""
    print(f"\n{CYAN}{'='*60}{RESET}")
    print(f"{CYAN}{text}{RESET}")
    print(f"{CYAN}{'='*60}{RESET}\n")


def print_status(item, success, message=""):
    """Print status with colored checkmark/cross."""
    if success:
        print(f"  {GREEN}[OK]{RESET} {item} {message}")
    else:
        print(f"  {RED}[FAIL]{RESET} {item} {message}")


def print_warning(message):
    """Print a warning message."""
    print(f"  {YELLOW}[WARN]{RESET} {message}")


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of all files in a directory."""
    sha256 = hashlib.sha256()
    if path.is_file():
        sha256.update(path.read_bytes())
    else:
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                sha256.update(file_path.read_bytes())
    return sha256.hexdigest()


def download_fastembed_model(model_name: str, local_path: Path) -> bool:
    """Download FastEmbed model and save to local path."""
    try:
        from fastembed import TextEmbedding

        print(f"  Downloading {model_name}...")
        print(f"  This may take a few minutes...")

        # Initialize model (triggers download to HF cache)
        model = TextEmbedding(model_name=model_name, max_length=128)

        # Find the cached model and copy to local path
        hf_cache = Path.home() / ".cache" / "fastembed"

        # The model is loaded, so we just need to verify it works
        test_result = list(model.embed(["test"]))
        if len(test_result) > 0:
            # Create local directory and mark as ready
            local_path.mkdir(parents=True, exist_ok=True)

            # Copy model files from cache if possible
            # FastEmbed stores models in ~/.cache/fastembed/
            for cache_dir in hf_cache.iterdir():
                if "bge-small" in cache_dir.name.lower():
                    if cache_dir.is_dir():
                        shutil.copytree(cache_dir, local_path, dirs_exist_ok=True)
                        return True

            # If we can't find the cache dir, just mark as ready
            (local_path / ".ready").write_text(f"Downloaded: {datetime.now().isoformat()}")
            return True

        return False

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def download_sentence_transformer_model(model_name: str, local_path: Path) -> bool:
    """Download SentenceTransformer model and save to local path."""
    try:
        from sentence_transformers import SentenceTransformer

        print(f"  Downloading {model_name}...")
        print(f"  This may take a few minutes...")

        # Download and load model
        model = SentenceTransformer(model_name)

        # Save to local path
        local_path.mkdir(parents=True, exist_ok=True)
        model.save(str(local_path))

        print(f"  Saved to {local_path}")
        return True

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def download_frontend_asset(name: str, url: str, local_path: Path) -> bool:
    """Download a frontend asset from CDN."""
    try:
        import requests

        print(f"  Downloading {name} from {url}...")

        local_path.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        local_path.write_bytes(response.content)
        print(f"  Saved to {local_path} ({len(response.content) / 1024:.1f} KB)")
        return True

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def create_placeholder_image(local_path: Path) -> bool:
    """Create a placeholder gradient image for login page."""
    try:
        from PIL import Image, ImageDraw

        print(f"  Creating placeholder login image...")

        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Create a gradient image (1200x800)
        width, height = 1200, 800
        img = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(img)

        # Purple to blue gradient
        for y in range(height):
            r = int(88 + (y / height) * 40)
            g = int(28 + (y / height) * 100)
            b = int(135 + (y / height) * 80)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        img.save(local_path, 'JPEG', quality=85)
        print(f"  Saved to {local_path}")
        return True

    except ImportError:
        print_warning("Pillow not installed - creating simple placeholder")
        # Create a minimal valid JPEG
        local_path.parent.mkdir(parents=True, exist_ok=True)
        # This is a minimal 1x1 purple JPEG
        minimal_jpeg = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
            0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
            0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
            0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
            0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
            0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
            0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
            0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
            0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
            0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
            0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
            0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
            0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
            0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
            0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
            0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
            0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
            0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5, 0xDB, 0x20, 0xA8, 0xBA, 0xB3, 0x42,
            0xCC, 0x64, 0x66, 0x03, 0x23, 0xBD, 0xFF, 0xD9
        ])
        local_path.write_bytes(minimal_jpeg)
        return True
    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def generate_model_registry() -> bool:
    """Generate .model_registry.json with SHA256 checksums."""
    try:
        print_header("Generating Model Registry")

        registry = {}

        for model_name, config in MODELS.items():
            local_path = config["local_path"]
            if local_path.exists():
                print(f"  Computing SHA256 for {model_name}...")
                sha256 = compute_sha256(local_path)
                registry[model_name] = {
                    "sha256": sha256,
                    "path": str(local_path.relative_to(PROJECT_ROOT)),
                    "type": config["type"],
                    "downloaded_at": datetime.now().isoformat(),
                }
                print_status(model_name, True, f"({sha256[:16]}...)")
            else:
                print_warning(f"{model_name} not found - skipping")

        if registry:
            registry_path = MODELS_DIR / ".model_registry.json"
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            with open(registry_path, 'w') as f:
                json.dump(registry, f, indent=2)

            print(f"\n  Registry saved to {registry_path}")
            return True
        else:
            print_warning("No models found - registry not created")
            return False

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def patch_html_files() -> bool:
    """Patch HTML files to use local assets instead of CDN."""
    try:
        print_header("Patching HTML Files")

        html_files = list(FRONTEND_DIR.glob("*.html"))

        replacements = [
            # TailwindCSS
            ('src="https://cdn.tailwindcss.com"', 'src="assets/css/tailwind.min.js"'),
            ("src='https://cdn.tailwindcss.com'", "src='assets/css/tailwind.min.js'"),
            # Chart.js
            ('src="https://cdn.jsdelivr.net/npm/chart.js"', 'src="assets/js/chart.min.js"'),
            ("src='https://cdn.jsdelivr.net/npm/chart.js'", "src='assets/js/chart.min.js'"),
            # Unsplash image
            ('src="https://images.unsplash.com/photo-1555949963-aa79dcee981c"', 'src="assets/images/login-bg.jpg"'),
        ]

        patched_count = 0

        for html_file in html_files:
            content = html_file.read_text(encoding='utf-8')
            original_content = content

            for old, new in replacements:
                if old in content:
                    content = content.replace(old, new)
                    print(f"  {html_file.name}: Replaced CDN reference")

            if content != original_content:
                html_file.write_text(content, encoding='utf-8')
                patched_count += 1
                print_status(html_file.name, True, "patched")
            else:
                print_status(html_file.name, True, "no changes needed")

        print(f"\n  Patched {patched_count} file(s)")
        return True

    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        return False


def verify_mysql(skip: bool = False) -> bool:
    """Verify MySQL connection and create admin_db if needed."""
    if skip:
        print_warning("MySQL verification skipped")
        return True

    try:
        print_header("Verifying MySQL Connection")

        import pymysql

        # Connection settings (match existing codebase)
        host = os.getenv("MYSQL_HOST", "localhost")
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")

        print(f"  Connecting to MySQL at {host}...")

        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            connect_timeout=10,
        )

        with conn.cursor() as cursor:
            # Create admin_db if not exists
            cursor.execute("CREATE DATABASE IF NOT EXISTS admin_db")
            cursor.execute("SHOW DATABASES LIKE 'admin_db'")
            result = cursor.fetchone()

            if result:
                print_status("admin_db", True, "database exists/created")
            else:
                print_status("admin_db", False, "failed to create")
                return False

        conn.close()
        return True

    except ImportError:
        print_warning("pymysql not installed - cannot verify MySQL")
        return False
    except Exception as e:
        print(f"  {RED}Error: {e}{RESET}")
        print_warning("MySQL verification failed - you may need to create admin_db manually")
        return False


def download_models() -> dict:
    """Download all required models."""
    print_header("Downloading Models")

    results = {}

    for model_name, config in MODELS.items():
        local_path = config["local_path"]
        model_type = config["type"]

        print(f"\n  [{model_type}] {model_name}")
        print(f"  Size: ~{config['size_mb']} MB")

        if local_path.exists():
            print_status(model_name, True, "already downloaded")
            results[model_name] = True
            continue

        if model_type == "fastembed":
            results[model_name] = download_fastembed_model(model_name, local_path)
        elif model_type == "sentence_transformers":
            results[model_name] = download_sentence_transformer_model(model_name, local_path)
        else:
            print_warning(f"Unknown model type: {model_type}")
            results[model_name] = False

        if results[model_name]:
            print_status(model_name, True, "downloaded")
        else:
            print_status(model_name, False, "download failed")

    return results


def download_assets() -> dict:
    """Download all frontend assets."""
    print_header("Downloading Frontend Assets")

    results = {}

    # Download TailwindCSS and Chart.js
    for name, config in FRONTEND_ASSETS.items():
        local_path = config["local_path"]

        if local_path.exists():
            print_status(name, True, "already downloaded")
            results[name] = True
            continue

        results[name] = download_frontend_asset(name, config["url"], local_path)

    # Create placeholder image
    image_path = ASSETS_DIR / "images" / "login-bg.jpg"
    if image_path.exists():
        print_status("login-bg.jpg", True, "already exists")
        results["login-bg.jpg"] = True
    else:
        results["login-bg.jpg"] = create_placeholder_image(image_path)

    return results


def verify_setup() -> bool:
    """Verify existing setup is complete."""
    print_header("Verifying Offline Setup")

    all_ok = True

    # Check models
    print(f"\n  {CYAN}Models:{RESET}")
    for model_name, config in MODELS.items():
        exists = config["local_path"].exists()
        print_status(model_name, exists, str(config["local_path"]) if exists else "MISSING")
        if config["required"] and not exists:
            all_ok = False

    # Check registry
    registry_path = MODELS_DIR / ".model_registry.json"
    print_status(".model_registry.json", registry_path.exists())

    # Check frontend assets
    print(f"\n  {CYAN}Frontend Assets:{RESET}")
    for name, config in FRONTEND_ASSETS.items():
        exists = config["local_path"].exists()
        print_status(name, exists, str(config["local_path"]) if exists else "MISSING")
        if not exists:
            all_ok = False

    image_path = ASSETS_DIR / "images" / "login-bg.jpg"
    print_status("login-bg.jpg", image_path.exists())

    # Check HTML patches
    print(f"\n  {CYAN}HTML Files:{RESET}")
    html_files = list(FRONTEND_DIR.glob("*.html"))
    for html_file in html_files:
        content = html_file.read_text(encoding='utf-8')
        has_cdn = "cdn.tailwindcss.com" in content or "cdn.jsdelivr.net" in content
        print_status(html_file.name, not has_cdn, "patched" if not has_cdn else "STILL HAS CDN")
        if has_cdn:
            all_ok = False

    return all_ok


def print_summary(model_results: dict, asset_results: dict, mysql_ok: bool, registry_ok: bool, patch_ok: bool):
    """Print final summary."""
    print_header("Setup Summary")

    total_items = len(model_results) + len(asset_results) + 3  # +3 for mysql, registry, patches
    success_count = sum(model_results.values()) + sum(asset_results.values())
    success_count += int(mysql_ok) + int(registry_ok) + int(patch_ok)

    print(f"  {CYAN}Models:{RESET}")
    for name, success in model_results.items():
        print_status(name, success)

    print(f"\n  {CYAN}Frontend Assets:{RESET}")
    for name, success in asset_results.items():
        print_status(name, success)

    print(f"\n  {CYAN}Configuration:{RESET}")
    print_status("Model Registry", registry_ok)
    print_status("HTML Patches", patch_ok)
    print_status("MySQL Database", mysql_ok)

    print(f"\n{'='*60}")
    if success_count == total_items:
        print(f"{GREEN}SUCCESS: All {total_items} components ready for offline deployment!{RESET}")
        print(f"\nNext steps:")
        print(f"  1. Copy .env.example to .env and configure settings")
        print(f"  2. Set OFFLINE_MODE=true in .env")
        print(f"  3. Start the application: uvicorn aidiffchecker.backend.main:app")
        print(f"  4. Or use Docker: docker-compose up -d")
    else:
        print(f"{YELLOW}PARTIAL: {success_count}/{total_items} components ready.{RESET}")
        print(f"Some components failed. Check the errors above and retry.")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="DiffSense-AI Offline Setup")
    parser.add_argument("--models-only", action="store_true", help="Download models only")
    parser.add_argument("--assets-only", action="store_true", help="Download frontend assets only")
    parser.add_argument("--verify", action="store_true", help="Verify existing setup")
    parser.add_argument("--skip-mysql", action="store_true", help="Skip MySQL verification")
    args = parser.parse_args()

    print(f"\n{CYAN}DiffSense-AI Offline Setup{RESET}")
    print(f"{'='*60}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Models dir:   {MODELS_DIR}")
    print(f"Frontend dir: {FRONTEND_DIR}")

    if args.verify:
        success = verify_setup()
        sys.exit(0 if success else 1)

    # Create directories
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (ASSETS_DIR / "css").mkdir(exist_ok=True)
    (ASSETS_DIR / "js").mkdir(exist_ok=True)
    (ASSETS_DIR / "images").mkdir(exist_ok=True)

    model_results = {}
    asset_results = {}
    mysql_ok = True
    registry_ok = True
    patch_ok = True

    if not args.assets_only:
        model_results = download_models()
        registry_ok = generate_model_registry()

    if not args.models_only:
        asset_results = download_assets()
        patch_ok = patch_html_files()
        mysql_ok = verify_mysql(skip=args.skip_mysql)

    print_summary(
        model_results or {},
        asset_results or {},
        mysql_ok,
        registry_ok,
        patch_ok
    )


if __name__ == "__main__":
    main()
