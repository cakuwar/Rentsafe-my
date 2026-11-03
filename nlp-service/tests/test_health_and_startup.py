"""GET /health, and loading the layer-2 model at server startup.

Like test_classify_endpoint.py, these call the app's coroutines directly rather
than through a test client, so they need no extra HTTP dependency. The startup
tests drive the real `lifespan` and the real loader; only transformers'
from_pretrained is replaced, so no weights are read and nothing is downloaded.
"""
import asyncio
from types import SimpleNamespace

import pytest

from app import main
from app.layer2 import classifier

CONVERSATION = "\n".join([
    "Renter: Hi, is the room still available?",
    "Owner: Yes it is. When do you plan to move in?",
    "Renter: Early next month. Can I view it first?",
    "Owner: Sure, come by on Saturday.",
    "Renter: How much is the deposit?",
    "Owner: Two months, paid after you view and sign.",
])


def start_server():
    """Run the app's startup, as uvicorn does before taking requests."""
    async def startup():
        async with main.lifespan(main.app):
            pass
    asyncio.run(startup())


@pytest.fixture
def nothing_loaded(monkeypatch):
    """No model and no load attempts yet; the real state is restored after."""
    for name, value in (("_model", None), ("_tokenizer", None), ("_load_attempts", 0),
                        ("_scam_index", 1), ("_temperature", 1.0)):
        monkeypatch.setattr(classifier, name, value)


@pytest.fixture
def from_pretrained(monkeypatch, nothing_loaded):
    """Script what each attempt to load the weights does.

    Each call to the returned function sets the outcome of the next attempts
    in order: an exception is raised, anything else loads a stand-in model.
    Returns the list of attempts made, for counting.
    """
    transformers = pytest.importorskip("transformers")
    outcomes, attempts = [], []

    def tokenizer(*args, **kwargs):
        attempts.append(args)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return "tokenizer"

    def model(*args, **kwargs):
        return SimpleNamespace(
            eval=lambda: None,
            config=SimpleNamespace(label2id={"LEGITIMATE": 0, "SCAM": 1}),
            num_parameters=lambda: 0,
        )

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", tokenizer)
    monkeypatch.setattr(
        transformers.AutoModelForSequenceClassification, "from_pretrained", model
    )

    def script(*next_outcomes):
        outcomes.extend(next_outcomes)
        return attempts
    return script


# --- /health -----------------------------------------------------------------

def test_health_is_ok():
    assert asyncio.run(main.health()) == {"status": "ok"}


def test_health_is_a_get_route():
    methods = {route.path: route.methods for route in main.app.routes
               if hasattr(route, "methods")}
    assert "GET" in methods["/health"]


def test_health_does_not_load_the_model(monkeypatch, nothing_loaded):
    loads = []
    monkeypatch.setattr(classifier, "_load", lambda: loads.append(1))
    asyncio.run(main.health())
    assert loads == []
    assert classifier._model is None


# --- loading at startup ------------------------------------------------------

def test_startup_loads_the_model(monkeypatch):
    loads = []
    monkeypatch.setattr(main, "l2_load", lambda: loads.append(1))
    start_server()
    assert loads == [1]


def test_startup_survives_a_failed_load(from_pretrained):
    """The server must come up, so /health and /docs still answer."""
    attempts = from_pretrained(OSError("simulated: repository not found"))
    start_server()   # raises if a failed load escapes the lifespan
    assert len(attempts) == 1
    assert asyncio.run(main.health()) == {"status": "ok"}


def test_classify_retries_the_load_once_after_a_failed_startup(from_pretrained):
    attempts = from_pretrained(*[OSError("simulated: Hub unreachable")] * 3)
    start_server()                                   # attempt 1
    first = classifier.classify(CONVERSATION)        # attempt 2, the one retry
    second = classifier.classify(CONVERSATION)       # gives up until restart
    assert len(attempts) == classifier.MAX_LOAD_ATTEMPTS == 2
    assert first["status"] == second["status"] == "model_unavailable"


def test_a_successful_retry_recovers_the_model(from_pretrained):
    """A transient failure at startup does not leave the service without a model."""
    attempts = from_pretrained(OSError("simulated: Hub unreachable"), "ok")
    start_server()
    assert classifier._model is None
    tokenizer, model = classifier._load()            # what /classify calls
    assert model is not None
    assert len(attempts) == 2
