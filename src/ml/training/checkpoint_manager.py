"""
Checkpoint Manager for Helios Neural Network Training

Manages model checkpoints, saves best models, handles early stopping.
"""

import torch
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import shutil

from src.utils.logger import get_logger

logger = get_logger(__name__, component="checkpoint_manager")


class CheckpointManager:
    """
    Manages model checkpoints during training.

    Features:
    - Saves best model based on validation metric
    - Implements early stopping
    - Manages checkpoint history
    - Provides checkpoint loading utilities
    """

    def __init__(
        self,
        checkpoint_dir: str = "models/checkpoints",
        best_model_path: str = "models/helios_neural_network_40m_best.pt",
        monitor_metric: str = "val_acc",
        mode: str = "max",
        patience: int = 15,
        save_top_k: int = 3
    ):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to save checkpoints
            best_model_path: Path to save best model
            monitor_metric: Metric to monitor (e.g., "val_acc", "val_loss")
            mode: "max" for accuracy, "min" for loss
            patience: Early stopping patience
            save_top_k: Number of top checkpoints to keep
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.best_model_path = Path(best_model_path)
        self.best_model_path.parent.mkdir(parents=True, exist_ok=True)

        self.monitor_metric = monitor_metric
        self.mode = mode
        self.patience = patience
        self.save_top_k = save_top_k

        # Tracking
        self.best_metric = float('-inf') if mode == 'max' else float('inf')
        self.patience_counter = 0
        self.checkpoint_history = []

        logger.info(f"CheckpointManager initialized:")
        logger.info(f"  Monitor: {monitor_metric} ({mode})")
        logger.info(f"  Patience: {patience}")
        logger.info(f"  Save top-{save_top_k} checkpoints")

    def save_checkpoint(
        self,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        epoch: int,
        metrics: Dict[str, float],
        config: Dict[str, Any] = None,
        scheduler: Optional[torch.optim.lr_scheduler._LRScheduler] = None
    ) -> bool:
        """
        Save a checkpoint if it improves the monitored metric.

        Args:
            model: PyTorch model
            optimizer: Optimizer
            epoch: Current epoch
            metrics: Dictionary of metrics (must include monitor_metric)
            config: Optional training configuration
            scheduler: Optional learning rate scheduler

        Returns:
            True if checkpoint was saved, False otherwise
        """
        if self.monitor_metric not in metrics:
            logger.warning(f"Monitor metric '{self.monitor_metric}' not in metrics")
            return False

        current_metric = metrics[self.monitor_metric]

        # Check if this is the best model
        is_best = self._is_better(current_metric, self.best_metric)

        if is_best:
            self.best_metric = current_metric
            self.patience_counter = 0

            # Save best model
            checkpoint = {
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'metrics': metrics,
                'best_metric': self.best_metric,
                'config': config,
                'timestamp': datetime.utcnow().isoformat()
            }

            if scheduler is not None:
                checkpoint['scheduler_state_dict'] = scheduler.state_dict()

            # Save to best model path
            torch.save(checkpoint, self.best_model_path)
            logger.info(f"✓ Best model saved: {self.best_model_path}")
            logger.info(f"  {self.monitor_metric}: {current_metric:.4f}")

            # Also save to checkpoint directory with epoch number
            epoch_checkpoint_path = self.checkpoint_dir / f"checkpoint_epoch_{epoch:03d}.pt"
            torch.save(checkpoint, epoch_checkpoint_path)

            # Update checkpoint history
            self.checkpoint_history.append({
                "epoch": epoch,
                "path": str(epoch_checkpoint_path),
                "metric": current_metric,
                "timestamp": checkpoint['timestamp']
            })

            # Cleanup old checkpoints (keep top-k)
            self._cleanup_old_checkpoints()

            return True
        else:
            self.patience_counter += 1
            logger.info(
                f"No improvement in {self.monitor_metric}. "
                f"Patience: {self.patience_counter}/{self.patience}"
            )
            return False

    def should_stop_early(self) -> bool:
        """
        Check if training should stop early.

        Returns:
            True if patience exceeded
        """
        return self.patience_counter >= self.patience

    def load_checkpoint(
        self,
        checkpoint_path: str,
        model: torch.nn.Module,
        optimizer: Optional[torch.optim.Optimizer] = None,
        scheduler: Optional[torch.optim.lr_scheduler._LRScheduler] = None,
        device: torch.device = None
    ) -> Dict[str, Any]:
        """
        Load a checkpoint.

        Args:
            checkpoint_path: Path to checkpoint file
            model: Model to load state into
            optimizer: Optional optimizer to load state into
            scheduler: Optional scheduler to load state into
            device: Device to load checkpoint on

        Returns:
            Checkpoint dictionary
        """
        if device is None:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        checkpoint = torch.load(checkpoint_path, map_location=device)

        model.load_state_dict(checkpoint['model_state_dict'])

        if optimizer is not None and 'optimizer_state_dict' in checkpoint:
            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

        if scheduler is not None and 'scheduler_state_dict' in checkpoint:
            scheduler.load_state_dict(checkpoint['scheduler_state_dict'])

        logger.info(f"Checkpoint loaded: {checkpoint_path}")
        logger.info(f"  Epoch: {checkpoint['epoch']}")
        if 'metrics' in checkpoint:
            logger.info(f"  Metrics: {checkpoint['metrics']}")

        return checkpoint

    def load_best_model(
        self,
        model: torch.nn.Module,
        device: torch.device = None
    ) -> Dict[str, Any]:
        """
        Load the best model.

        Args:
            model: Model to load state into
            device: Device to load model on

        Returns:
            Checkpoint dictionary
        """
        return self.load_checkpoint(
            str(self.best_model_path),
            model,
            device=device
        )

    def get_checkpoint_history(self) -> list:
        """Get checkpoint history."""
        return self.checkpoint_history

    def save_checkpoint_history(self, filepath: str = None):
        """
        Save checkpoint history to JSON.

        Args:
            filepath: Path to save history (default: checkpoint_dir/history.json)
        """
        if filepath is None:
            filepath = self.checkpoint_dir / "history.json"

        with open(filepath, 'w') as f:
            json.dump({
                "best_metric": self.best_metric,
                "monitor_metric": self.monitor_metric,
                "mode": self.mode,
                "checkpoint_history": self.checkpoint_history
            }, f, indent=2)

        logger.info(f"Checkpoint history saved: {filepath}")

    def _is_better(self, current: float, best: float) -> bool:
        """Check if current metric is better than best."""
        if self.mode == 'max':
            return current > best
        else:
            return current < best

    def _cleanup_old_checkpoints(self):
        """Remove old checkpoints, keeping only top-k."""
        if len(self.checkpoint_history) <= self.save_top_k:
            return

        # Sort by metric (best first)
        sorted_history = sorted(
            self.checkpoint_history,
            key=lambda x: x['metric'],
            reverse=(self.mode == 'max')
        )

        # Keep top-k
        keep_paths = {item['path'] for item in sorted_history[:self.save_top_k]}

        # Remove old checkpoints
        removed_count = 0
        for item in self.checkpoint_history:
            if item['path'] not in keep_paths and Path(item['path']).exists():
                Path(item['path']).unlink()
                removed_count += 1

        # Update history
        self.checkpoint_history = sorted_history[:self.save_top_k]

        if removed_count > 0:
            logger.info(f"Removed {removed_count} old checkpoints (keeping top-{self.save_top_k})")

    def get_best_checkpoint_info(self) -> Dict[str, Any]:
        """Get information about the best checkpoint."""
        if not self.best_model_path.exists():
            return None

        checkpoint = torch.load(self.best_model_path, map_location='cpu')

        return {
            "path": str(self.best_model_path),
            "epoch": checkpoint.get('epoch'),
            "metrics": checkpoint.get('metrics'),
            "best_metric": self.best_metric,
            "timestamp": checkpoint.get('timestamp')
        }


def create_checkpoint_manager(
    config: Any,
    checkpoint_dir: str = None,
    best_model_path: str = None
) -> CheckpointManager:
    """
    Create a checkpoint manager from training config.

    Args:
        config: Training configuration object
        checkpoint_dir: Optional custom checkpoint directory
        best_model_path: Optional custom best model path

    Returns:
        CheckpointManager instance
    """
    if checkpoint_dir is None:
        checkpoint_dir = config.model_save_dir + "/checkpoints"

    if best_model_path is None:
        best_model_path = config.checkpoint_path

    return CheckpointManager(
        checkpoint_dir=checkpoint_dir,
        best_model_path=best_model_path,
        monitor_metric="val_acc",
        mode="max",
        patience=config.patience,
        save_top_k=3
    )
