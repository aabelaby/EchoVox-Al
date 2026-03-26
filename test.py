import sys
import torch
import torch.nn.functional as F
from pathlib import Path
from sklearn.preprocessing import LabelEncoder

sys.path.insert(0, ".")
from lip_reading_train import (
    LipReadingModel, build_face_landmarker,
    extract_mouth_frames
)


def predict(video_path, checkpoint="checkpoints/best_model.pt"):
    dev  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(checkpoint, map_location=dev, weights_only=False)

    model = LipReadingModel(ckpt["cfg"]).to(dev)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    # ── Correct label lookup ────────────────────────────────────
    # LabelEncoder sorts alphabetically during fit(), so the model's
    # output index 0,1,2... maps to le.classes_ NOT to the SENTENCES list.
    # Always read the sentence list from the saved checkpoint.
    if "sentences" in ckpt:
        # Saved correctly as le.classes_ order
        sentences = ckpt["sentences"]
    elif "label_enc" in ckpt:
        # Fall back to reading from the saved LabelEncoder
        sentences = list(ckpt["label_enc"].classes_)
    else:
        raise ValueError("Checkpoint has no label mapping. Retrain with fixed script.")

    print(f"\nLabel mapping in this checkpoint (model output → sentence):")
    for i, s in enumerate(sentences):
        print(f"  {i} → {s}")

    # ── MediaPipe landmarker ────────────────────────────────────
    lmk = None
    mp_path = ckpt["cfg"].get("mediapipe_model", "face_landmarker.task")
    if Path(mp_path).exists():
        try:
            lmk = build_face_landmarker(mp_path)
        except Exception:
            pass

    # ── Extract frames & run inference ─────────────────────────
    f = extract_mouth_frames(video_path, ckpt["cfg"], lmk)
    if lmk:
        lmk.close()
    if f is None:
        return {"error": "No face detected in video"}

    x = torch.tensor(f).permute(0, 3, 1, 2).unsqueeze(0).float().to(dev)
    with torch.no_grad():
        probs = F.softmax(model(x), dim=1)[0]

    idx = probs.argmax().item()

    return {
        "predicted_sentence" : sentences[idx],
        "confidence"         : round(probs[idx].item(), 4),
        "all_probs"          : {s: round(p.item(), 4)
                                for s, p in zip(sentences, probs)},
    }


# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    video      = sys.argv[1] if len(sys.argv) > 1 else r"echovox_LipSync_Dataset\videos\Sentence2_02.mp4"
    checkpoint = sys.argv[2] if len(sys.argv) > 2 else "checkpoints/best_model.pt"

    print(f"Video     : {video}")
    print(f"Checkpoint: {checkpoint}")

    result = predict(video, checkpoint)

    if "error" in result:
        print(f"\nERROR: {result['error']}")
        sys.exit(1)

    print("\n" + "="*55)
    print(f"  Prediction : {result['predicted_sentence']}")
    print(f"  Confidence : {result['confidence']:.4f}  ({result['confidence']*100:.1f}%)")
    print("="*55)
    print("\nAll class probabilities:")
    for sent, prob in sorted(result["all_probs"].items(),
                             key=lambda x: x[1], reverse=True):
        bar = "#" * int(prob * 40)
        print(f"  {prob:.4f}  {bar:<40}  {sent}")