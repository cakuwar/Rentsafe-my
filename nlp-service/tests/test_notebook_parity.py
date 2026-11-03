"""The service must score exactly the way train_colab_v3.ipynb evaluates.

The notebook's acceptance criteria are measured with its own `windowed_margin`
and `probability` functions. If the service scored differently — another window
size or stride, mean instead of max, the temperature ignored — an accepted model
would behave differently in production from how it was judged.

These tests pull those two functions out of the notebook file itself (so an edit
to the notebook is tested, not a copy of it) and compare them with
`app.layer2.classifier` on a small randomly initialised XLM-R saved with a
`calibration_temperature`. A random model gives each window a different score,
so a wrong aggregation or a missed window cannot agree by accident.
"""
import ast
import json
import os

import pytest

from app import config
from app.layer2 import classifier

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

NLP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTEBOOK = os.path.join(NLP, "train_colab_v3.ipynb")
TOKENIZER_DIR = os.path.join(NLP, "models", "xlm-roberta-scam-random")
TEMPERATURE = 1.7

SHORT = "Renter: Is the room still available?\nOwner: Yes, you can view it on Saturday."
LONG = "\n".join(
    f"{'Renter' if i % 2 else 'Owner'}: message {i} about the unit in "
    f"{['Cheras', 'Kajang', 'Puchong', 'Bangi'][i % 4]}, deposit RM{300 + i * 10}, "
    f"viewing on day {i % 7} and keys handed over in person"
    for i in range(70)
)


FUNCTIONS = ("message_windows", "windowed_margin", "probability")


def notebook_functions(namespace):
    """Exec the notebook's own scoring functions, and its STRIDE, into namespace."""
    with open(NOTEBOOK, encoding="utf-8") as handle:
        cells = ["".join(c["source"]) for c in json.load(handle)["cells"]
                 if c["cell_type"] == "code"]
    source = next(c for c in cells if "def windowed_margin" in c)
    wanted = [node for node in ast.parse(source).body
              if (isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS)
              or (isinstance(node, ast.Assign)
                  and any(getattr(t, "id", None) == "STRIDE" for t in node.targets))]
    assert len(wanted) == len(FUNCTIONS) + 1, "notebook scoring code has changed shape"
    exec(compile(ast.Module(body=wanted, type_ignores=[]), NOTEBOOK, "exec"), namespace)
    return namespace["windowed_margin"], namespace["probability"]


@pytest.fixture(scope="module")
def tiny_checkpoint(tmp_path_factory):
    if not os.path.isdir(TOKENIZER_DIR):
        pytest.skip("tokenizer not present (models/ is not in the repo)")
    from transformers import (AutoTokenizer, XLMRobertaConfig,
                              XLMRobertaForSequenceClassification)

    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_DIR)
    torch.manual_seed(0)
    model_config = XLMRobertaConfig(
        vocab_size=tokenizer.vocab_size, hidden_size=32, num_hidden_layers=2,
        num_attention_heads=2, intermediate_size=64, max_position_embeddings=514,
        initializer_range=0.5,   # default 0.02 gives near-identical window scores
        num_labels=2, id2label={0: "LEGITIMATE", 1: "SCAM"},
        label2id={"LEGITIMATE": 0, "SCAM": 1},
    )
    model = XLMRobertaForSequenceClassification(model_config)
    model.config.calibration_temperature = TEMPERATURE   # as the notebook saves it
    path = tmp_path_factory.mktemp("tiny-xlmr")
    model.save_pretrained(path)
    tokenizer.save_pretrained(path)
    return str(path)


@pytest.fixture
def service(tiny_checkpoint, monkeypatch):
    """The classifier pointed at the tiny checkpoint, with a clean load state."""
    monkeypatch.setattr(config, "FINETUNED_MODEL_DIR", tiny_checkpoint)
    for name, value in (("_model", None), ("_tokenizer", None), ("_load_attempts", 0),
                        ("_scam_index", 1), ("_temperature", 1.0)):
        monkeypatch.setattr(classifier, name, value)
    tokenizer, model = classifier._load()
    assert model is not None
    return tokenizer, model


@pytest.fixture
def notebook(tiny_checkpoint, service):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    best = AutoModelForSequenceClassification.from_pretrained(tiny_checkpoint).eval()
    namespace = {
        "torch": torch, "np": np, "MAX_LENGTH": 512, "device": best.device,
        "tokenizer": AutoTokenizer.from_pretrained(tiny_checkpoint), "best": best,
        "scam_index": 1, "legit_index": 0,
    }
    windowed_margin, probability = notebook_functions(namespace)
    saved = json.load(open(os.path.join(tiny_checkpoint, "config.json")))
    return windowed_margin, probability, saved["calibration_temperature"]


def test_the_service_reads_the_temperature_the_notebook_saves(service, notebook):
    _, _, saved = notebook
    assert saved == TEMPERATURE
    assert classifier._temperature == TEMPERATURE


def test_long_input_really_spans_several_different_windows(service):
    tokenizer, _ = service
    windows = classifier._message_windows(tokenizer, LONG)
    assert len(windows) >= 3, "fixture too short to exercise windowing"
    scores = classifier._window_scores(LONG)
    assert len(scores) == len(windows)
    assert max(scores) - min(scores) > 1e-4, "windows must differ for the test to bite"


@pytest.mark.parametrize("text", [SHORT, LONG], ids=["one window", "several windows"])
def test_service_probability_equals_the_notebook(notebook, text):
    windowed_margin, probability, temperature = notebook
    expected = float(probability(windowed_margin(text), temperature))
    assert classifier._model_probability(text) == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize("text", [SHORT, LONG], ids=["one window", "several windows"])
def test_classify_reports_the_notebook_number(notebook, text):
    windowed_margin, probability, temperature = notebook
    expected = float(probability(windowed_margin(text), temperature))
    assert classify_model_probability(text) == pytest.approx(expected, abs=1e-4)


def test_the_temperature_actually_changes_the_number(notebook):
    """Guards against a service that reads the temperature but never applies it."""
    windowed_margin, probability, temperature = notebook
    margin = windowed_margin(LONG)
    assert float(probability(margin, temperature)) != pytest.approx(
        float(probability(margin, 1.0)), abs=1e-4)
    assert classifier._model_probability(LONG) == pytest.approx(
        float(probability(margin, temperature)), abs=1e-5)


def classify_model_probability(text):
    return classifier.classify(text)["model_probability"]


def test_notebook_and_service_cut_identical_windows(notebook, service):
    """Same windows, token for token, including an over-long single message."""
    tokenizer, _ = service
    namespace = notebook_namespace_of(notebook)
    over_long = "Owner: " + " ".join(f"word{i}" for i in range(700))
    for text in (SHORT, LONG, "\n".join([LONG, over_long, "Renter: ok"])):
        assert namespace["message_windows"](text) == classifier._message_windows(tokenizer, text)


def notebook_namespace_of(notebook):
    windowed_margin, _, _ = notebook
    return windowed_margin.__globals__
