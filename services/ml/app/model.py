import os, torch, random

ATTRIBUTE_KEYS = [
    "uneven_tone_appearance",
    "hyperpigmentation_appearance",
    "redness_appearance",
    "texture_roughness_appearance",
    "shine_oiliness_appearance",
    "pore_visibility_appearance",
    "fine_lines_appearance",
    "dryness_flaking_appearance",
]

class InferenceModel:
    def __init__(self):
        self.version = os.getenv("MODEL_VERSION", "0.1.0-mvp")
        self.path = os.getenv("TORCH_MODEL_PATH", "")
        self.torch_model = None
        if self.path and os.path.exists(self.path):
            try:
                self.torch_model = torch.jit.load(self.path, map_location="cpu")
                self.torch_model.eval()
            except Exception:
                self.torch_model = None

    def infer(self, img_bgr):
        # If a real torchscript model is loaded, call it here.
        # MVP: deterministic-ish pseudo outputs to keep API stable.
        rnd = random.Random(int(img_bgr.sum()) % 10_000_000)

        out = []
        for k in ATTRIBUTE_KEYS:
            score = rnd.random()
            conf = 0.45 + 0.4 * rnd.random()
            out.append({"key": k, "score": round(score, 4), "confidence": round(conf, 4)})
        return out

model = InferenceModel()
