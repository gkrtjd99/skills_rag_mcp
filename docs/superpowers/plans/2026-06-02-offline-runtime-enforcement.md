# Offline Runtime Enforcement Plan

Status: Implemented

## Steps

- [x] Add a shared helper that sets Hugging Face offline environment variables
  when local-files-only mode is enabled.
- [x] Call it before lazy sentence-transformers model loading.
- [x] Call it before lazy MarianMT model loading.
- [x] Add tests proving both model-load paths set offline mode before import.
- [x] Re-run pytest and fixture eval.
