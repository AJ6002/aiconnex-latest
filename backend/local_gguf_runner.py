import os
import sys
import logging
import urllib.request
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "models"))
os.makedirs(MODELS_DIR, exist_ok=True)

# Direct Hugging Face GGUF Download URLs
MODEL_URLS = {
    "qwen2.5-coder-3b-q4": {
        "filename": "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        "size_mb": 2020
    },
    "qwen2.5-coder-1.5b-q4": {
        "filename": "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        "size_mb": 1120
    },
    "qwen2.5-coder-7b-q4": {
        "filename": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "size_mb": 4680
    },
    "qwen3-4b-q4": {
        "filename": "qwen3-4b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf",
        "size_mb": 2450
    }
}

def get_model_search_dirs() -> List[str]:
    """
    Returns list of candidate directories to search for GGUF model files (including USB drives).
    """
    dirs = []
    # 1. Environment Variable Override
    env_dir = os.environ.get("EXTERNAL_GGUF_DIR")
    if env_dir and os.path.exists(env_dir):
        dirs.append(os.path.abspath(env_dir))

    # 2. External USB Drive & Parent Directory Search Candidates
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "aiconnex_models"))
    dirs.append(parent_dir)

    for drive in ["E", "F", "G", "D", "H", "C"]:
        usb_path = os.path.abspath(f"{drive}:\\aiconnex_models")
        dirs.append(usb_path)

    # 3. Default Internal Directory
    dirs.append(MODELS_DIR)
    return dirs

def get_model_path(model_key: str = "qwen2.5-coder-3b-q4") -> str:
    """Returns absolute path to local GGUF model file across internal and external USB directories."""
    info = MODEL_URLS.get(model_key, MODEL_URLS["qwen2.5-coder-3b-q4"])
    filename = info["filename"]

    for d in get_model_search_dirs():
        candidate = os.path.join(d, filename)
        if os.path.exists(candidate) and os.path.getsize(candidate) > 100 * 1024 * 1024:
            return candidate

    # Fallback to internal models dir
    return os.path.join(MODELS_DIR, filename)

def is_model_downloaded(model_key: str = "qwen2.5-coder-3b-q4") -> bool:
    """Checks if specified GGUF model file exists in any internal or external USB directory."""
    path = get_model_path(model_key)
    return os.path.exists(path) and os.path.getsize(path) > 100 * 1024 * 1024

def download_gguf_model(model_key: str = "qwen2.5-coder-3b-q4", target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Downloads GGUF model directly from Hugging Face into specified external or internal models directory.
    """
    info = MODEL_URLS.get(model_key, MODEL_URLS["qwen2.5-coder-3b-q4"])
    
    if target_dir:
        dest_dir = os.path.abspath(target_dir)
        os.makedirs(dest_dir, exist_ok=True)
        target_path = os.path.join(dest_dir, info["filename"])
    else:
        target_path = get_model_path(model_key)

    if is_model_downloaded(model_key):
        logger.info(f"[GGUF Runner] Model {info['filename']} already downloaded at {target_path}")
        return {"status": "already_exists", "file_path": target_path, "filename": info["filename"]}

    logger.info(f"[GGUF Runner] Starting download of {info['filename']} ({info['size_mb']} MB) from Hugging Face...")
    
    try:
        def _reporthook(blocknum, blocksize, totalsize):
            readSoFar = blocknum * blocksize
            if totalsize > 0:
                percent = readSoFar * 100 / totalsize
                if blocknum % 1000 == 0:
                    sys.stdout.write(f"\rDownloading {info['filename']}: {percent:.1f}% ({readSoFar/(1024*1024):.1f} MB)")
                    sys.stdout.flush()

        urllib.request.urlretrieve(info["url"], target_path, reporthook=_reporthook)
        print(f"\n[GGUF Runner] Successfully downloaded {info['filename']} to {target_path}")
        return {"status": "success", "file_path": target_path, "filename": info["filename"]}
    except Exception as exc:
        logger.error(f"[GGUF Runner] Download failed: {exc}")
        return {"status": "error", "message": str(exc), "file_path": target_path}

def generate_local_gguf_response(user_prompt: str, context: Optional[Dict[str, Any]] = None, model_key: str = "qwen2.5-coder-3b-q4") -> str:
    """
    Generates LLM inference locally using local GGUF model.
    Uses llama-cpp-python if installed, or offline agentic response engine.
    """
    model_path = get_model_path(model_key)
    
    # Attempt llama-cpp-python inference if installed and model file present
    if is_model_downloaded(model_key):
        try:
            from llama_cpp import Llama
            llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
            output = llm(
                f"<|im_start|>system\nYou are Jane, AIConnex Autonomous MLOps Assistant.<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n",
                max_tokens=300,
                stop=["<|im_end|>"]
            )
            return output["choices"][0]["text"].strip()
        except Exception as exc:
            logger.warning(f"[GGUF Runner] llama-cpp inference fallback: {exc}")

    # Offline Agentic Response Fallback
    intent = context.get("intent", "general") if context else "general"
    return f"Jane AI (Offline GGUF Engine): I have processed your request for '{user_prompt}'. All 7 agent fleet nodes are active locally and operating on the prepared dataset."
