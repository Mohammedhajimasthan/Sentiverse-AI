import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models.emotion import _build_model as build_emotion_model
from backend.models.fake_review import _build_model as build_fake_model
from backend.models.sarcasm import _build_model as build_sarcasm_model

MODEL_BUILDERS = {
    "emotion": build_emotion_model,
    "sarcasm": build_sarcasm_model,
    "fake_review": build_fake_model,
}


def train_all_models():
    artifacts = {}
    for name, builder in MODEL_BUILDERS.items():
        model = builder()
        if model is None:
            artifacts[name] = {"status": "skipped", "reason": "scikit-learn not available"}
            continue
        path = ROOT / "models" / f"{name}_model.joblib"
        import joblib
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)
        artifacts[name] = {"status": "trained", "path": str(path)}
    return artifacts


if __name__ == "__main__":
    result = train_all_models()
    print(json.dumps(result, indent=2))
