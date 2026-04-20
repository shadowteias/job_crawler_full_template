from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


TRANSFORMERS_REPO = "Qwen/Qwen2.5-0.5B"
GGUF_REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
GGUF_FILENAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download local model assets after clone without storing them in git.",
    )
    parser.add_argument(
        "--models-dir",
        default="models",
        help="Local directory where models will be downloaded (default: models)",
    )
    parser.add_argument(
        "--skip-transformers",
        action="store_true",
        help="Skip downloading the Qwen transformers checkpoint directory",
    )
    parser.add_argument(
        "--skip-gguf",
        action="store_true",
        help="Skip downloading the GGUF file used for llama.cpp-style local inference",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_transformers:
        target_dir = models_dir / "qwen2.5-0.5b"
        print(f"Downloading transformers checkpoint into {target_dir} ...")
        snapshot_download(
            repo_id=TRANSFORMERS_REPO,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False,
        )

    if not args.skip_gguf:
        print(f"Downloading GGUF into {models_dir / GGUF_FILENAME} ...")
        hf_hub_download(
            repo_id=GGUF_REPO,
            filename=GGUF_FILENAME,
            local_dir=str(models_dir),
            local_dir_use_symlinks=False,
        )

    print("Model download bootstrap complete.")


if __name__ == "__main__":
    main()
