"""
Model Evaluator for Helios Neural Network

Provides comprehensive evaluation metrics and analysis tools.
"""

import torch
import numpy as np
import pandas as pd
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_recall_fscore_support,
    roc_auc_score
)
from typing import Dict, List, Tuple, Any
import json
from pathlib import Path
from datetime import datetime

from src.utils.logger import get_logger

logger = get_logger(__name__, component="model_evaluator")


class ModelEvaluator:
    """
    Comprehensive model evaluation toolkit.

    Provides metrics, confusion matrices, classification reports,
    and performance analysis for the Helios neural network.
    """

    def __init__(self, class_names: List[str] = None):
        """
        Initialize evaluator.

        Args:
            class_names: List of class names (default: ["BUY", "SELL", "HOLD"])
        """
        self.class_names = class_names or ["BUY", "SELL", "HOLD"]

    def evaluate_model(
        self,
        model: torch.nn.Module,
        dataloader: torch.utils.data.DataLoader,
        device: torch.device,
        use_amp: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate model on a dataset.

        Args:
            model: Trained PyTorch model
            dataloader: DataLoader with evaluation data
            device: Device to run evaluation on
            use_amp: Use automatic mixed precision

        Returns:
            Dictionary with comprehensive metrics
        """
        model.eval()

        all_predictions = []
        all_labels = []
        all_probabilities = []
        all_confidences = []

        with torch.no_grad():
            for features, labels in dataloader:
                features, labels = features.to(device), labels.to(device)

                if use_amp:
                    with torch.cuda.amp.autocast():
                        predictions, confidence = model(features)
                else:
                    predictions, confidence = model(features)

                # Get predicted classes
                _, predicted = torch.max(predictions, 1)

                # Store results
                all_predictions.extend(predicted.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                all_probabilities.extend(predictions.cpu().numpy())
                all_confidences.extend(confidence.cpu().numpy().flatten())

        # Convert to numpy arrays
        y_true = np.array(all_labels)
        y_pred = np.array(all_predictions)
        y_proba = np.array(all_probabilities)
        confidences = np.array(all_confidences)

        # Calculate metrics
        metrics = self._calculate_metrics(y_true, y_pred, y_proba, confidences)

        return metrics

    def _calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray,
        confidences: np.ndarray
    ) -> Dict[str, Any]:
        """Calculate comprehensive evaluation metrics."""

        # Overall accuracy
        accuracy = accuracy_score(y_true, y_pred)

        # Per-class metrics
        precision, recall, f1, support = precision_recall_fscore_support(
            y_true, y_pred, average=None, zero_division=0
        )

        # Weighted averages
        precision_avg, recall_avg, f1_avg, _ = precision_recall_fscore_support(
            y_true, y_pred, average='weighted', zero_division=0
        )

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred)

        # Classification report
        class_report = classification_report(
            y_true, y_pred,
            target_names=self.class_names,
            output_dict=True,
            zero_division=0
        )

        # Confidence statistics
        confidence_stats = {
            "mean": float(np.mean(confidences)),
            "std": float(np.std(confidences)),
            "min": float(np.min(confidences)),
            "max": float(np.max(confidences)),
            "median": float(np.median(confidences))
        }

        # Per-class confidence
        class_confidence = {}
        for i, class_name in enumerate(self.class_names):
            class_mask = y_pred == i
            if class_mask.sum() > 0:
                class_confidence[class_name] = {
                    "mean": float(np.mean(confidences[class_mask])),
                    "std": float(np.std(confidences[class_mask])),
                    "count": int(class_mask.sum())
                }

        # ROC AUC (one-vs-rest for multiclass)
        try:
            roc_auc = roc_auc_score(y_true, y_proba, multi_class='ovr', average='weighted')
        except ValueError:
            roc_auc = None

        metrics = {
            "accuracy": float(accuracy),
            "precision_weighted": float(precision_avg),
            "recall_weighted": float(recall_avg),
            "f1_weighted": float(f1_avg),
            "roc_auc": float(roc_auc) if roc_auc is not None else None,
            "confusion_matrix": cm.tolist(),
            "classification_report": class_report,
            "confidence_stats": confidence_stats,
            "class_confidence": class_confidence,
            "per_class_metrics": {
                self.class_names[i]: {
                    "precision": float(precision[i]),
                    "recall": float(recall[i]),
                    "f1": float(f1[i]),
                    "support": int(support[i])
                }
                for i in range(len(self.class_names))
            },
            "total_samples": len(y_true),
            "timestamp": datetime.utcnow().isoformat()
        }

        return metrics

    def print_evaluation_report(self, metrics: Dict[str, Any]):
        """
        Print a formatted evaluation report.

        Args:
            metrics: Metrics dictionary from evaluate_model()
        """
        print("\n" + "=" * 80)
        print("  MODEL EVALUATION REPORT")
        print("=" * 80)
        print()

        # Overall metrics
        print("Overall Performance:")
        print("-" * 80)
        print(f"  Accuracy:          {metrics['accuracy']:.4f}")
        print(f"  Precision (avg):   {metrics['precision_weighted']:.4f}")
        print(f"  Recall (avg):      {metrics['recall_weighted']:.4f}")
        print(f"  F1 Score (avg):    {metrics['f1_weighted']:.4f}")
        if metrics['roc_auc'] is not None:
            print(f"  ROC AUC:           {metrics['roc_auc']:.4f}")
        print()

        # Per-class metrics
        print("Per-Class Performance:")
        print("-" * 80)
        for class_name, class_metrics in metrics['per_class_metrics'].items():
            print(f"\n  {class_name}:")
            print(f"    Precision:  {class_metrics['precision']:.4f}")
            print(f"    Recall:     {class_metrics['recall']:.4f}")
            print(f"    F1 Score:   {class_metrics['f1']:.4f}")
            print(f"    Support:    {class_metrics['support']}")
        print()

        # Confusion matrix
        print("Confusion Matrix:")
        print("-" * 80)
        cm = np.array(metrics['confusion_matrix'])

        # Header
        header = "         " + "  ".join([f"{name:>8}" for name in self.class_names])
        print(header)
        print("-" * len(header))

        # Rows
        for i, row in enumerate(cm):
            row_str = f"{self.class_names[i]:>8} " + "  ".join([f"{val:>8}" for val in row])
            print(row_str)
        print()

        # Confidence statistics
        print("Confidence Statistics:")
        print("-" * 80)
        conf_stats = metrics['confidence_stats']
        print(f"  Mean:    {conf_stats['mean']:.4f}")
        print(f"  Std:     {conf_stats['std']:.4f}")
        print(f"  Min:     {conf_stats['min']:.4f}")
        print(f"  Max:     {conf_stats['max']:.4f}")
        print(f"  Median:  {conf_stats['median']:.4f}")
        print()

        # Per-class confidence
        if 'class_confidence' in metrics and metrics['class_confidence']:
            print("Per-Class Confidence:")
            print("-" * 80)
            for class_name, conf in metrics['class_confidence'].items():
                print(f"  {class_name}:")
                print(f"    Mean:  {conf['mean']:.4f}")
                print(f"    Std:   {conf['std']:.4f}")
                print(f"    Count: {conf['count']}")
            print()

        print("=" * 80)
        print(f"  Total Samples: {metrics['total_samples']}")
        print("=" * 80)
        print()

    def save_metrics(self, metrics: Dict[str, Any], filepath: str):
        """
        Save metrics to JSON file.

        Args:
            metrics: Metrics dictionary
            filepath: Path to save JSON file
        """
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w') as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"Metrics saved to {filepath}")

    def compare_models(
        self,
        metrics_list: List[Dict[str, Any]],
        model_names: List[str]
    ) -> pd.DataFrame:
        """
        Compare multiple models.

        Args:
            metrics_list: List of metrics dictionaries
            model_names: List of model names

        Returns:
            DataFrame with comparison
        """
        comparison_data = []

        for name, metrics in zip(model_names, metrics_list):
            comparison_data.append({
                "Model": name,
                "Accuracy": metrics['accuracy'],
                "Precision": metrics['precision_weighted'],
                "Recall": metrics['recall_weighted'],
                "F1 Score": metrics['f1_weighted'],
                "ROC AUC": metrics['roc_auc'],
                "Avg Confidence": metrics['confidence_stats']['mean'],
                "Samples": metrics['total_samples']
            })

        df = pd.DataFrame(comparison_data)
        return df

    def analyze_errors(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        confidences: np.ndarray,
        features: np.ndarray = None
    ) -> Dict[str, Any]:
        """
        Analyze prediction errors.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            confidences: Confidence scores
            features: Optional feature array

        Returns:
            Error analysis report
        """
        # Find misclassified samples
        errors = y_true != y_pred
        error_indices = np.where(errors)[0]

        error_analysis = {
            "total_errors": int(errors.sum()),
            "error_rate": float(errors.mean()),
            "error_breakdown": {},
            "confidence_of_errors": {
                "mean": float(np.mean(confidences[errors])) if errors.sum() > 0 else 0.0,
                "std": float(np.std(confidences[errors])) if errors.sum() > 0 else 0.0
            }
        }

        # Breakdown by true class
        for i, class_name in enumerate(self.class_names):
            class_mask = y_true == i
            class_errors = errors & class_mask

            if class_mask.sum() > 0:
                error_analysis["error_breakdown"][class_name] = {
                    "total": int(class_mask.sum()),
                    "errors": int(class_errors.sum()),
                    "error_rate": float(class_errors.sum() / class_mask.sum())
                }

        return error_analysis
