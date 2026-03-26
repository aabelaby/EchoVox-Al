"""
=====================================================================
  EchoVox LipSync — Full Lip Reading Training Pipeline
  CNN + LSTM | 7-Class Sentence Classification
  Compatible with MediaPipe 0.10+
=====================================================================
Dataset structure:
    echovox_LipSync_Dataset/
        metadata/labels.xlsx
        videos/Sentence1_01.mp4 ...
Usage:
    conda activate lipread_env
    python lip_reading_train.py
=====================================================================
"""

import os, sys, time, random, logging, warnings, urllib.request
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

import cv2

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import torchvision.models as models

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────
CFG = {
    "dataset_root"      : "echovox_LipSync_Dataset",
    "video_dir"         : "echovox_LipSync_Dataset/videos",
    "metadata_path"     : "echovox_LipSync_Dataset/metadata/labels.xlsx",
    "cache_dir"         : "echovox_LipSync_Dataset/processed_frames",
    "checkpoint_dir"    : "checkpoints",
    "log_file"          : "training.log",
    "mediapipe_model"   : "face_landmarker.task",

    "max_frames"        : 40,
    "img_size"          : 96,
    "use_grayscale"     : False,

    "num_classes"       : 7,
    "lstm_hidden"       : 256,
    "lstm_layers"       : 2,
    "dropout"           : 0.4,

    "epochs"            : 60,
    "batch_size"        : 16,
    "lr"                : 1e-4,
    "weight_decay"      : 1e-4,
    "patience"          : 12,
    "val_split"         : 0.15,
    "test_split"        : 0.10,
    "seed"              : 42,

    "augment"           : True,
    "brightness_jitter" : 0.3,
    "contrast_jitter"   : 0.3,
}

SENTENCES = [
    "Please buy me a completely new phone",
    "The weather is very beautiful today",
    "Are you going to the market tomorrow",
    "She saw a shiny silver car outside",
    "We are working on a visual project",
    "Can you open the door for me",
    "Artificial intelligence is changing the world",
]

MOUTH_LANDMARKS = [61,146,91,181,84,17,314,405,321,375,
                   78,95,88,178,87,14,317,402,318,324]

# ─────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────
# Force UTF-8 output on Windows (fixes arrow/tick encoding errors)
if hasattr(sys.stdout, "buffer"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(CFG["log_file"], encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def set_seed(seed):
    random.seed(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True


# ─────────────────────────────────────────────────────────────────
#  MEDIAPIPE SETUP  (Tasks API — MediaPipe 0.10+)
# ─────────────────────────────────────────────────────────────────
FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)

def ensure_mediapipe_model(model_path):
    if Path(model_path).exists():
        return
    log.info(f"Downloading MediaPipe model → {model_path}")
    try:
        urllib.request.urlretrieve(FACE_LANDMARKER_URL, model_path)
        log.info("Download complete.")
    except Exception as e:
        raise RuntimeError(
            f"Could not auto-download MediaPipe model.\n"
            f"Please download manually:\n  {FACE_LANDMARKER_URL}\n"
            f"Save as: {model_path}"
        ) from e


def build_face_landmarker(model_path):
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    opts = mp_vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
    )
    return mp_vision.FaceLandmarker.create_from_options(opts)


# ─────────────────────────────────────────────────────────────────
#  MOUTH EXTRACTION
# ─────────────────────────────────────────────────────────────────
def extract_mouth_frames(video_path, cfg, landmarker=None):
    import mediapipe as mp

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        log.warning(f"Cannot open: {video_path}")
        return None

    frames = []
    img_size   = cfg["img_size"]
    max_frames = cfg["max_frames"]
    use_gray   = cfg.get("use_grayscale", False)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]

        mouth = None
        if landmarker is not None:
            try:
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_img)
                if result.face_landmarks:
                    lm = result.face_landmarks[0]
                    xs = [int(lm[i].x * w) for i in MOUTH_LANDMARKS]
                    ys = [int(lm[i].y * h) for i in MOUTH_LANDMARKS]
                    pad = 14
                    x1 = max(min(xs)-pad,0); x2 = min(max(xs)+pad,w)
                    y1 = max(min(ys)-pad,0); y2 = min(max(ys)+pad,h)
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        mouth = cv2.resize(crop, (img_size, img_size))
            except Exception:
                pass

        if mouth is None:
            lower = frame[h//2:, w//4: 3*w//4]
            mouth = cv2.resize(lower if lower.size > 0 else frame,
                               (img_size, img_size))

        if use_gray:
            mouth = cv2.cvtColor(mouth, cv2.COLOR_BGR2GRAY)
            mouth = np.expand_dims(mouth, -1)
        else:
            mouth = cv2.cvtColor(mouth, cv2.COLOR_BGR2RGB)
        frames.append(mouth)

    cap.release()
    if not frames:
        return None

    if len(frames) > max_frames:
        idx = np.linspace(0, len(frames)-1, max_frames, dtype=int)
        frames = [frames[i] for i in idx]
    while len(frames) < max_frames:
        frames.append(frames[-1])

    return np.stack(frames, 0).astype(np.float32) / 255.0


# ─────────────────────────────────────────────────────────────────
#  DATASET
# ─────────────────────────────────────────────────────────────────
class LipReadingDataset(Dataset):
    def __init__(self, records, cfg, augment=False):
        self.records   = records
        self.cfg       = cfg
        self.augment   = augment
        self.cache_dir = Path(cfg["cache_dir"])
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def __len__(self): return len(self.records)

    def _cp(self, vp): return self.cache_dir / (Path(vp).stem + ".npy")

    def _load(self, vp):
        cp = self._cp(vp)
        if cp.exists(): return np.load(cp)
        T = self.cfg["max_frames"]; C = 1 if self.cfg.get("use_grayscale") else 3
        return np.zeros((T, self.cfg["img_size"], self.cfg["img_size"], C), np.float32)

    def _aug(self, f):
        if random.random() < 0.5: f = f[:,:,::-1,:].copy()
        a = 1.0+random.uniform(-self.cfg["contrast_jitter"], self.cfg["contrast_jitter"])
        b = random.uniform(-self.cfg["brightness_jitter"], self.cfg["brightness_jitter"])
        f = np.clip(f*a+b, 0, 1)
        s = random.randint(-2, 2)
        if s > 0: f = np.concatenate([f[s:], np.repeat(f[-1:], s, 0)])
        elif s < 0: f = np.concatenate([np.repeat(f[:1], abs(s), 0), f[:s]])
        return f

    def __getitem__(self, idx):
        r = self.records[idx]
        f = self._load(r["video_path"])
        if self.augment and self.cfg["augment"]: f = self._aug(f)
        return (torch.tensor(f).permute(0,3,1,2).float(),
                torch.tensor(r["label_idx"], dtype=torch.long))


# ─────────────────────────────────────────────────────────────────
#  MODEL
# ─────────────────────────────────────────────────────────────────
class LipReadingModel(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        h = cfg["lstm_hidden"]; L = cfg["lstm_layers"]
        d = cfg["dropout"];     n = cfg["num_classes"]
        C = 1 if cfg.get("use_grayscale") else 3

        bb = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
        if C == 1: bb.conv1 = nn.Conv2d(1, 64, 7, 2, 3, bias=False)
        self.cnn = nn.Sequential(*list(bb.children())[:-1])
        self.fn  = nn.LayerNorm(512); self.fd = nn.Dropout(d)
        self.lstm = nn.LSTM(512, h, L, batch_first=True,
                            bidirectional=True, dropout=d if L>1 else 0.)
        self.cls = nn.Sequential(
            nn.LayerNorm(h*2), nn.Dropout(d),
            nn.Linear(h*2, 128), nn.GELU(),
            nn.Dropout(d/2), nn.Linear(128, n))

    def forward(self, x):
        B,T,C,H,W = x.shape
        f = self.cnn(x.view(B*T,C,H,W)).view(B,T,-1)
        f = self.fd(self.fn(f))
        o,_ = self.lstm(f)
        return self.cls(o.mean(1))


# ─────────────────────────────────────────────────────────────────
#  TRAIN / EVAL
# ─────────────────────────────────────────────────────────────────
class EarlyStopping:
    def __init__(self, p, mode="max"):
        self.p=p; self.mode=mode
        self.best=-np.inf if mode=="max" else np.inf
        self.c=0; self.stop=False
    def step(self, v):
        ok = v>self.best if self.mode=="max" else v<self.best
        if ok: self.best=v; self.c=0
        else:
            self.c+=1
            if self.c>=self.p: self.stop=True
        return ok


def train_one_epoch(model, dl, crit, opt, dev):
    model.train(); tl=tc=tot=0
    for v,l in dl:
        v,l=v.to(dev),l.to(dev); opt.zero_grad()
        o=model(v); loss=crit(o,l); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),5.)
        opt.step()
        tl+=loss.item()*l.size(0); tc+=(o.argmax(1)==l).sum().item(); tot+=l.size(0)
    return tl/tot, tc/tot


@torch.no_grad()
def evaluate(model, dl, crit, dev):
    model.eval(); tl=tc=tot=0; ap=[]; al=[]
    for v,l in dl:
        v,l=v.to(dev),l.to(dev); o=model(v); loss=crit(o,l)
        p=o.argmax(1)
        tl+=loss.item()*l.size(0); tc+=(p==l).sum().item(); tot+=l.size(0)
        ap.extend(p.cpu().numpy()); al.extend(l.cpu().numpy())
    return tl/tot, tc/tot, np.array(ap), np.array(al)


# ─────────────────────────────────────────────────────────────────
#  METADATA
# ─────────────────────────────────────────────────────────────────
def load_metadata(cfg):
    df = pd.read_excel(cfg["metadata_path"])
    log.info(f"Metadata: {len(df)} rows  cols={list(df.columns)}")
    fc=lc=None
    for c in df.columns:
        cl=c.lower()
        if any(k in cl for k in ("file","video","name")): fc=c
        if any(k in cl for k in ("text","label","sentence","spoken")): lc=c
    if fc is None: fc=df.columns[0]
    if lc is None: lc=df.columns[1]
    log.info(f"Columns: '{fc}' | '{lc}'")
    le=LabelEncoder(); le.fit(SENTENCES)
    recs=[]; miss=0
    for _,row in df.iterrows():
        fn=str(row[fc]).strip(); tx=str(row[lc]).strip()
        vp=Path(cfg["video_dir"])/fn
        if not vp.exists(): miss+=1; continue
        try: idx=le.transform([tx])[0]
        except ValueError: log.warning(f"Unknown label: {fn}"); continue
        recs.append({"video_path":str(vp),"label_idx":int(idx)})
    log.info(f"Records: {len(recs)} loaded | {miss} missing")
    return recs, le


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────
def main():
    set_seed(CFG["seed"])
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {dev}")
    Path(CFG["checkpoint_dir"]).mkdir(parents=True, exist_ok=True)

    # MediaPipe
    ensure_mediapipe_model(CFG["mediapipe_model"])
    try:
        lmk = build_face_landmarker(CFG["mediapipe_model"])
        log.info("MediaPipe FaceLandmarker ready.")
    except Exception as e:
        log.warning(f"MediaPipe failed ({e}) — using OpenCV fallback.")
        lmk = None

    # Data
    recs, le = load_metadata(CFG)
    labs = [r["label_idx"] for r in recs]
    tr, tmp = train_test_split(recs, test_size=CFG["val_split"]+CFG["test_split"],
                               stratify=labs, random_state=CFG["seed"])
    tl2=[r["label_idx"] for r in tmp]
    vr=CFG["val_split"]/(CFG["val_split"]+CFG["test_split"])
    va, te = train_test_split(tmp, test_size=1-vr, stratify=tl2, random_state=CFG["seed"])
    log.info(f"Split → train:{len(tr)}  val:{len(va)}  test:{len(te)}")

    # Cache
    log.info("Caching mouth frames (runs once) …")
    cd = Path(CFG["cache_dir"]); cd.mkdir(parents=True, exist_ok=True)
    all_r = tr+va+te
    for i,r in enumerate(all_r, 1):
        cp = cd/(Path(r["video_path"]).stem+".npy")
        if not cp.exists():
            f = extract_mouth_frames(r["video_path"], CFG, lmk)
            if f is None:
                T=CFG["max_frames"]; C=1 if CFG.get("use_grayscale") else 3
                f=np.zeros((T,CFG["img_size"],CFG["img_size"],C),np.float32)
            np.save(cp, f)
        if i%50==0 or i==len(all_r): log.info(f"  {i}/{len(all_r)} cached")

    if lmk: lmk.close()
    log.info("Caching done.")

    nw = 0 if os.name=="nt" else 4
    mkdl = lambda ds,sh: DataLoader(ds, CFG["batch_size"], shuffle=sh,
                                    num_workers=nw, pin_memory=True)
    tr_dl = mkdl(LipReadingDataset(tr, CFG, True),  True)
    va_dl = mkdl(LipReadingDataset(va, CFG, False), False)
    te_dl = mkdl(LipReadingDataset(te, CFG, False), False)

    model   = LipReadingModel(CFG).to(dev)
    crit    = nn.CrossEntropyLoss(label_smoothing=0.1)
    opt     = torch.optim.AdamW(model.parameters(), lr=CFG["lr"],
                                weight_decay=CFG["weight_decay"])
    sched   = torch.optim.lr_scheduler.CosineAnnealingLR(opt, CFG["epochs"], 1e-6)
    stopper = EarlyStopping(CFG["patience"])
    log.info(f"Params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

    best_ckpt = Path(CFG["checkpoint_dir"])/"best_model.pt"
    hist = defaultdict(list)

    for epoch in range(1, CFG["epochs"]+1):
        t0=time.time()
        trl, tra = train_one_epoch(model, tr_dl, crit, opt, dev)
        vll, vla, _,_ = evaluate(model, va_dl, crit, dev)
        sched.step()
        for k,v in zip(["tr_loss","tr_acc","vl_loss","vl_acc"],[trl,tra,vll,vla]):
            hist[k].append(v)
        log.info(f"Epoch {epoch:3d}/{CFG['epochs']}  "
                 f"tr={trl:.4f}/{tra:.4f}  vl={vll:.4f}/{vla:.4f}  "
                 f"lr={sched.get_last_lr()[0]:.2e}  [{time.time()-t0:.1f}s]")
        if stopper.step(vla):
            torch.save({"epoch":epoch,"model_state":model.state_dict(),
                        "val_acc":vla,"cfg":CFG,"label_enc":le,
                        "sentences":list(le.classes_)}, best_ckpt)
            log.info(f"  ✓ Best saved (val_acc={vla:.4f})")
        if stopper.stop: log.info(f"Early stop @ epoch {epoch}"); break

    # Test
    log.info("\n"+"="*60+"\nFINAL TEST")
    model.load_state_dict(torch.load(best_ckpt, map_location=dev, weights_only=False)["model_state"])
    tel, tea, preds, labs2 = evaluate(model, te_dl, crit, dev)
    log.info(f"Test: loss={tel:.4f}  acc={tea:.4f} ({tea*100:.2f}%)")
    log.info("\n"+classification_report(labs2, preds,
        target_names=[f"S{i+1}" for i in range(CFG["num_classes"])]))
    log.info("Confusion Matrix:\n"+str(confusion_matrix(labs2, preds)))

    final = Path(CFG["checkpoint_dir"])/"final_model.pt"
    # IMPORTANT: use le.classes_ (alphabetically sorted by LabelEncoder)
    # NOT the hardcoded SENTENCES list — they are in different order!
    torch.save({"model_state":model.state_dict(),"cfg":CFG,
                "label_enc":le,"sentences":list(le.classes_)}, final)
    pd.DataFrame(hist).to_csv(Path(CFG["checkpoint_dir"])/"training_history.csv", index=False)
    log.info(f"Done. Final model → {final}")


# ─────────────────────────────────────────────────────────────────
#  INFERENCE
# ─────────────────────────────────────────────────────────────────
def predict(video_path, checkpoint="checkpoints/final_model.pt"):
    dev  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(checkpoint, map_location=dev, weights_only=False)
    model = LipReadingModel(ckpt["cfg"]).to(dev)
    model.load_state_dict(ckpt["model_state"]); model.eval()
    lmk = None
    mp_path = ckpt["cfg"].get("mediapipe_model","face_landmarker.task")
    if Path(mp_path).exists():
        try: lmk = build_face_landmarker(mp_path)
        except Exception: pass
    f = extract_mouth_frames(video_path, ckpt["cfg"], lmk)
    if lmk: lmk.close()
    if f is None: return {"error":"No face detected"}
    x = torch.tensor(f).permute(0,3,1,2).unsqueeze(0).float().to(dev)
    with torch.no_grad(): probs = F.softmax(model(x),1)[0]
    idx = probs.argmax().item(); sents = ckpt["sentences"]
    return {"predicted_sentence": sents[idx],
            "confidence": round(probs[idx].item(),4),
            "all_probs": {s:round(p.item(),4) for s,p in zip(sents,probs)}}


if __name__ == "__main__":
    main()