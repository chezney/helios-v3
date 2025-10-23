"""
PyTorch Dataset for Helios Trading System.
"""

import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class TradingDataset(Dataset):
    """PyTorch dataset for trading data."""

    def __init__(self, features: np.ndarray, labels: np.ndarray):
        """
        Initialize dataset.

        Args:
            features: numpy array of shape (n_samples, 90)
            labels: numpy array of shape (n_samples,) with values 0,1,2
        """
        self.features = torch.FloatTensor(features)
        self.labels = torch.LongTensor(labels)

        logger.info(
            f"TradingDataset created: {len(self)} samples, "
            f"features shape={self.features.shape}"
        )

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]


def create_dataloaders(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    batch_size: int = 16,
    num_workers: int = 4,
    pin_memory: bool = True,
) -> Tuple[DataLoader, DataLoader]:
    """
    Create train and validation DataLoaders.

    Args:
        X_train: Training features (n_samples, 90)
        y_train: Training labels (n_samples,)
        X_val: Validation features
        y_val: Validation labels
        batch_size: Batch size
        num_workers: Number of data loading workers
        pin_memory: Pin memory for faster GPU transfer

    Returns:
        Tuple of (train_loader, val_loader)
    """
    train_dataset = TradingDataset(X_train, y_train)
    val_dataset = TradingDataset(X_val, y_val)

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    logger.info(
        f"DataLoaders created: train={len(train_loader)} batches, "
        f"val={len(val_loader)} batches"
    )

    return train_loader, val_loader
