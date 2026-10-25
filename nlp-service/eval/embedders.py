"""Sentence embedders for the semantic red-flag experiment (eval/semantic_flags.py).

Two candidates, each loaded the way its model card says:

  intfloat/multilingual-e5-base
      mean pooling over tokens; every input prefixed "query: " (the card's
      advice for symmetric similarity tasks); L2-normalised.

  mesolitica/embedding-malaysian-mistral-64M-32k
      the model's own `encode` (loaded with trust_remote_code - the remote file,
      mistral_contrastive.py, was read before use: a Mistral model plus one
      linear layer, pooling the last non-pad token; no file or network access);
      right padding, as its pooling assumes; L2-normalised.

Embeddings are cached per text, since the corpus repeats many lines.
"""
import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

E5 = "intfloat/multilingual-e5-base"
MESOLITICA = "mesolitica/embedding-malaysian-mistral-64M-32k"
# Pinned: the revision whose mistral_contrastive.py was read before use
# (sha256 d60e3c6bbd4b416a...), so a later upstream change cannot run unread.
MESOLITICA_REVISION = "ca29fada4e4d2ae2c303d0803926d51c9c21f287"
MAX_TOKENS = 256          # a message; nothing in the data comes close


class Embedder:
    def __init__(self, name: str, batch_size: int = 32):
        self.name = name
        self.batch_size = batch_size
        self.cache: dict[str, np.ndarray] = {}
        if name == E5:
            self.tokenizer = AutoTokenizer.from_pretrained(name)
            self.model = AutoModel.from_pretrained(name).eval()
        elif name == MESOLITICA:
            self.tokenizer = AutoTokenizer.from_pretrained(name, revision=MESOLITICA_REVISION)
            self.tokenizer.padding_side = "right"
            self.model = AutoModel.from_pretrained(
                name, trust_remote_code=True, revision=MESOLITICA_REVISION).eval()
        else:
            raise ValueError(f"unknown embedder {name}")

    def _forward(self, texts: list[str]) -> np.ndarray:
        if self.name == E5:
            batch = self.tokenizer([f"query: {t}" for t in texts], padding=True,
                                   truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            with torch.no_grad():
                hidden = self.model(**batch).last_hidden_state
            mask = batch["attention_mask"].unsqueeze(-1).float()
            vectors = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        else:
            batch = self.tokenizer(texts, padding=True, truncation=True,
                                   max_length=MAX_TOKENS, return_tensors="pt")
            # Mistral takes no token_type_ids; the tokenizer adds them anyway.
            features = {"input_ids": batch["input_ids"], "attention_mask": batch["attention_mask"]}
            with torch.no_grad():
                vectors = self.model.encode(features)
        vectors = torch.nn.functional.normalize(vectors.float(), dim=-1)
        return vectors.numpy()

    def encode(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self.cache]
        for start in range(0, len(missing), self.batch_size):
            chunk = missing[start:start + self.batch_size]
            for text, vector in zip(chunk, self._forward(chunk)):
                self.cache[text] = vector
        return np.stack([self.cache[t] for t in texts]) if texts else np.zeros((0, 768))
