"""Runtime configuration for the NLP service, read from environment."""
import os
from pathlib import Path

# PRIMARY_MODEL is the base model of the fine-tuned classifier in
# FINETUNED_MODEL_DIR. SECONDARY_MODEL and ZERO_SHOT_LABELS are NOT USED: a
# zero-shot second model was planned for calibration, tested, and dropped
# (eval/zero_shot_test.py, docs/MODEL_COMPARISON.md section 14.12). They are
# kept only so an old .env still loads.

SERVICE_DIR = Path(__file__).resolve().parents[1]


def _load_env_file(path):
	"""Read nlp-service/.env into os.environ without adding a dependency.

	Docker gets .env through compose's env_file, but a local `uvicorn app.main:app`
	would otherwise ignore it entirely and silently fall back to the defaults below.
	Real environment variables win, so exporting one still overrides the file.
	"""
	if not path.exists():
		return
	for line in path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, _, value = line.partition("=")
		os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(SERVICE_DIR / ".env")

TESSERACT_LANGS = os.getenv("TESSERACT_LANGS", "eng+msa")
NLP_PORT = int(os.getenv("NLP_PORT", 8000))
TESSDATA_DIR = os.getenv("TESSDATA_DIR", str(SERVICE_DIR / "tessdata"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "xlm-roberta-base")
SECONDARY_MODEL = os.getenv("SECONDARY_MODEL", "joeddav/xlm-roberta-large-xnli")


def _model_location(value):
	"""A local checkpoint folder, or else a Hugging Face Hub repo id.

	Relative paths (e.g. ./models/...) resolve against the service root, so the
	service works regardless of the directory it was started from. A value that
	is not an existing folder (e.g. cakuwar/rentsafe-xlmr-v3) is passed to
	from_pretrained unchanged and downloaded from the Hub. A private repo needs
	HF_TOKEN in the environment; huggingface_hub reads it itself.
	"""
	local = (SERVICE_DIR / value).resolve()
	return str(local) if local.is_dir() else value


FINETUNED_MODEL_DIR = _model_location(
	os.getenv("FINETUNED_MODEL_DIR", "models/xlm-roberta-scam-v3-run1")
)
ZERO_SHOT_LABELS = ["scam rental listing", "legitimate rental listing"]