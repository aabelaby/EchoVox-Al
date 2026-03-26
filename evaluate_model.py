"""Evaluate the trained lip reading model and print full metrics."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import torch
import numpy as np
from pathlib import Path
from torch.utils.data import DataLoader
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                             accuracy_score, precision_recall_fscore_support)

from lip_reading_train import (LipReadingModel, LipReadingDataset,
                                load_metadata, evaluate, CFG)

def main():
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt_path = Path("checkpoints/best_model.pt")
    ckpt = torch.load(ckpt_path, map_location=dev, weights_only=False)

    cfg = ckpt["cfg"]
    le = ckpt["label_enc"]
    sentences = list(le.classes_)

    # Recreate the same train/val/test split
    recs, _ = load_metadata(cfg)
    labs = [r["label_idx"] for r in recs]
    tr, tmp = train_test_split(recs, test_size=cfg["val_split"]+cfg["test_split"],
                               stratify=labs, random_state=cfg["seed"])
    tl2 = [r["label_idx"] for r in tmp]
    vr = cfg["val_split"] / (cfg["val_split"] + cfg["test_split"])
    va, te = train_test_split(tmp, test_size=1-vr, stratify=tl2, random_state=cfg["seed"])

    print(f"Dataset split -> Train: {len(tr)}  Val: {len(va)}  Test: {len(te)}")
    print(f"Device: {dev}")
    print(f"Best epoch: {ckpt.get('epoch', '?')}")
    print(f"Best val_acc: {ckpt.get('val_acc', '?')}")
    print()

    # Load model
    model = LipReadingModel(cfg).to(dev)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    import torch.nn as nn
    crit = nn.CrossEntropyLoss(label_smoothing=0.1)

    # Evaluate on TEST set
    te_dl = DataLoader(LipReadingDataset(te, cfg, False), cfg["batch_size"],
                       shuffle=False, num_workers=0, pin_memory=True)
    test_loss, test_acc, preds, labels = evaluate(model, te_dl, crit, dev)

    # Evaluate on VALIDATION set
    va_dl = DataLoader(LipReadingDataset(va, cfg, False), cfg["batch_size"],
                       shuffle=False, num_workers=0, pin_memory=True)
    val_loss, val_acc, val_preds, val_labels = evaluate(model, va_dl, crit, dev)

    # Evaluate on TRAIN set
    tr_dl = DataLoader(LipReadingDataset(tr, cfg, False), cfg["batch_size"],
                       shuffle=False, num_workers=0, pin_memory=True)
    train_loss, train_acc, _, _ = evaluate(model, tr_dl, crit, dev)

    names = [f"S{i+1}" for i in range(cfg["num_classes"])]

    print("=" * 70)
    print("PERFORMANCE EVALUATION METRICS")
    print("=" * 70)

    print(f"\n{'Set':<12} {'Loss':<10} {'Accuracy':<12}")
    print("-" * 34)
    print(f"{'Train':<12} {train_loss:<10.4f} {train_acc*100:<10.2f}%")
    print(f"{'Validation':<12} {val_loss:<10.4f} {val_acc*100:<10.2f}%")
    print(f"{'Test':<12} {test_loss:<10.4f} {test_acc*100:<10.2f}%")

    print("\n" + "=" * 70)
    print("PER-CLASS CLASSIFICATION REPORT (Test Set)")
    print("=" * 70)
    print(classification_report(labels, preds, target_names=names, digits=4))

    prec, rec, f1, sup = precision_recall_fscore_support(labels, preds, average=None)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(labels, preds, average='macro')
    weighted_p, weighted_r, weighted_f1, _ = precision_recall_fscore_support(labels, preds, average='weighted')

    print("=" * 70)
    print("SUMMARY METRICS (Test Set)")
    print("=" * 70)
    print(f"  Overall Accuracy     : {test_acc*100:.2f}%")
    print(f"  Macro Precision      : {macro_p*100:.2f}%")
    print(f"  Macro Recall         : {macro_r*100:.2f}%")
    print(f"  Macro F1-Score       : {macro_f1*100:.2f}%")
    print(f"  Weighted Precision   : {weighted_p*100:.2f}%")
    print(f"  Weighted Recall      : {weighted_r*100:.2f}%")
    print(f"  Weighted F1-Score    : {weighted_f1*100:.2f}%")

    print("\n" + "=" * 70)
    print("CONFUSION MATRIX (Test Set)")
    print("=" * 70)
    cm = confusion_matrix(labels, preds)
    # Header
    print(f"{'':>6}", end="")
    for n in names:
        print(f"{n:>6}", end="")
    print()
    for i, row in enumerate(cm):
        print(f"{names[i]:>6}", end="")
        for v in row:
            print(f"{v:>6}", end="")
        print()

    print("\n" + "=" * 70)
    print("SENTENCE MAPPING")
    print("=" * 70)
    for i, s in enumerate(sentences):
        print(f"  S{i+1}: {s}")

    # Training curve summary
    print("\n" + "=" * 70)
    print("TRAINING CURVE (from training_history.csv)")
    print("=" * 70)
    import csv
    hist_path = Path("checkpoints/training_history.csv")
    if hist_path.exists():
        with open(hist_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"  Total epochs trained: {len(rows)}")
        print(f"  Epoch 1  -> Train Acc: {float(rows[0]['tr_acc'])*100:.2f}%  Val Acc: {float(rows[0]['vl_acc'])*100:.2f}%")
        print(f"  Epoch {len(rows)} -> Train Acc: {float(rows[-1]['tr_acc'])*100:.2f}%  Val Acc: {float(rows[-1]['vl_acc'])*100:.2f}%")
        # Find best val acc epoch
        best_idx = max(range(len(rows)), key=lambda i: float(rows[i]['vl_acc']))
        print(f"  Best Val  -> Epoch {best_idx+1}: Val Acc: {float(rows[best_idx]['vl_acc'])*100:.2f}%")

if __name__ == "__main__":
    main()
