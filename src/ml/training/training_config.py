"""
Training configuration for Helios neural network.

Optimized for RTX 4060 (8GB/12GB VRAM) with FP16 and gradient checkpointing.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any
import torch


@dataclass
class TrainingConfig:
    """
    Training configuration for neural network.

    RTX 4060 8GB optimizations:
    - batch_size=16 (MANDATORY for 8GB VRAM)
    - mixed_precision=True (FP16 for memory savings)
    - gradient_checkpointing=True (saves 40% VRAM)
    """

    # Hardware
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    mixed_precision: bool = True
    gradient_checkpointing: bool = True

    # Batch configuration
    batch_size: int = 16
    accumulation_steps: int = 2  # Effective batch size = 32
    num_workers: int = 4
    pin_memory: bool = True
    prefetch_factor: int = 2

    # Model architecture
    hidden_lstm: int = 512
    hidden_gru: int = 256
    num_attention_heads: int = 8
    dropout: float = 0.3
    num_lstm_layers: int = 3
    num_gru_layers: int = 2

    # Training
    epochs: int = 100
    learning_rate: float = 0.001
    weight_decay: float = 1e-5

    # Early stopping
    patience: int = 15
    min_delta: float = 0.001

    # Learning rate scheduling
    scheduler_factor: float = 0.5
    scheduler_patience: int = 5

    # Label generation (60 candles = 1 hour look-ahead for better class balance)
    look_ahead_candles: int = 60  # Changed from 12 to 60 (1 hour instead of 12 minutes)
    buy_threshold_pct: float = 0.005  # 0.5% movement in 1 hour (more realistic for BTC)
    sell_threshold_pct: float = 0.005

    # Data split
    train_split: float = 0.8
    val_split: float = 0.2

    # Paths
    model_save_dir: str = "models"
    scaler_save_path: str = "models/scalers/feature_scaler_40m.pkl"
    checkpoint_path: str = "models/helios_neural_network_40m_best.pt"

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "TrainingConfig":
        """Create config from dictionary."""
        return cls(**config_dict)


def get_rtx4060_config(vram_gb: int = 8) -> TrainingConfig:
    """
    Get optimized configuration for RTX 4060.

    Args:
        vram_gb: VRAM size in GB (8 or 12)

    Returns:
        TrainingConfig optimized for RTX 4060
    """
    config = TrainingConfig()

    if vram_gb == 8:
        # 8GB configuration (CRITICAL optimizations)
        config.batch_size = 16
        config.mixed_precision = True
        config.gradient_checkpointing = True
    elif vram_gb == 12:
        # 12GB configuration (can relax some constraints)
        config.batch_size = 24
        config.mixed_precision = True
        config.gradient_checkpointing = True
    else:
        raise ValueError(f"Unsupported VRAM size: {vram_gb}GB. Use 8 or 12.")

    return config


def validate_config(config: TrainingConfig) -> bool:
    """
    Validate training configuration.

    Args:
        config: Training configuration

    Returns:
        True if valid

    Raises:
        ValueError: If configuration is invalid
    """
    # RTX 4060 8GB safety checks
    if config.device == "cuda":
        if torch.cuda.is_available():
            vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)

            if vram_gb <= 8.5:  # 8GB GPU
                if config.batch_size > 16:
                    raise ValueError(
                        f"batch_size={config.batch_size} too large for 8GB VRAM. "
                        f"Use batch_size <= 16"
                    )
                if not config.mixed_precision:
                    raise ValueError(
                        "mixed_precision=False on 8GB VRAM will cause OOM. "
                        "Set mixed_precision=True"
                    )
                if not config.gradient_checkpointing:
                    raise ValueError(
                        "gradient_checkpointing=False on 8GB VRAM will cause OOM. "
                        "Set gradient_checkpointing=True"
                    )

    # General validation
    if config.batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {config.batch_size}")

    if not (0 < config.learning_rate < 1):
        raise ValueError(f"learning_rate must be in (0, 1), got {config.learning_rate}")

    if not (0 <= config.dropout < 1):
        raise ValueError(f"dropout must be in [0, 1), got {config.dropout}")

    if not (0 < config.train_split < 1):
        raise ValueError(f"train_split must be in (0, 1), got {config.train_split}")

    return True
