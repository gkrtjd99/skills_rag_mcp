from __future__ import annotations

import os


def enforce_hf_offline(local_files_only: bool) -> None:
    """Force Hugging Face libraries into offline mode for runtime paths."""
    if not local_files_only:
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
