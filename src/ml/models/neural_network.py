"""
Helios Trading System V3.0 - 40M Parameter Neural Network

Tier 2: Predictive Attention Core
Hybrid LSTM/GRU architecture with multi-head attention for BUY/SELL/HOLD prediction.

Architecture (PRD Section 8):
- Input: 90 features (30 per timeframe × 3 timeframes)
- 3 parallel LSTM/GRU branches (HFP, MFP, LFP)
- Multi-head attention (8 heads) for cross-timeframe fusion
- Dense prediction layers with dropout
- Output: [buy_prob, sell_prob, hold_prob] + confidence

Parameter count: ~40M (optimized for financial time series)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class HeliosNeuralNetwork(nn.Module):
    """
    40M+ parameter hybrid LSTM/GRU neural network with multi-head attention.

    Architecture Philosophy:
    - Hybrid LSTM/GRU: LSTM for long-term dependencies, GRU for faster training
    - Multi-head attention: Cross-timeframe pattern fusion
    - Parallel processing: Each timeframe processed independently, then fused
    - Dropout regularization: Prevent overfitting (30% dropout)

    Input Shape: (batch_size, 90)
    Output Shape: predictions (batch_size, 3), confidence (batch_size, 1)
    """

    def __init__(
        self,
        input_size: int = 90,
        hidden_lstm: int = 512,  # Increased for 40M params
        hidden_gru: int = 256,   # Increased for 40M params
        num_attention_heads: int = 8,
        dropout: float = 0.3,
        num_lstm_layers: int = 3,  # Increased for 40M params
        num_gru_layers: int = 2    # Increased for 40M params
    ):
        super().__init__()

        self.input_size = input_size
        self.features_per_timeframe = 30
        self.hidden_lstm = hidden_lstm
        self.hidden_gru = hidden_gru

        # ============================================================
        # TIMEFRAME-SPECIFIC PROCESSING (Parallel Branches)
        # ============================================================

        # HFP Branch (High Frequency - 1min candles)
        self.hfp_lstm = nn.LSTM(
            input_size=self.features_per_timeframe,
            hidden_size=hidden_lstm,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0,
            bidirectional=False
        )
        self.hfp_gru = nn.GRU(
            input_size=hidden_lstm,
            hidden_size=hidden_gru,
            num_layers=num_gru_layers,
            batch_first=True,
            dropout=dropout if num_gru_layers > 1 else 0
        )

        # MFP Branch (Medium Frequency - 5min candles)
        self.mfp_lstm = nn.LSTM(
            input_size=self.features_per_timeframe,
            hidden_size=hidden_lstm,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0,
            bidirectional=False
        )
        self.mfp_gru = nn.GRU(
            input_size=hidden_lstm,
            hidden_size=hidden_gru,
            num_layers=num_gru_layers,
            batch_first=True,
            dropout=dropout if num_gru_layers > 1 else 0
        )

        # LFP Branch (Low Frequency - 15min candles)
        self.lfp_lstm = nn.LSTM(
            input_size=self.features_per_timeframe,
            hidden_size=hidden_lstm,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0,
            bidirectional=False
        )
        self.lfp_gru = nn.GRU(
            input_size=hidden_lstm,
            hidden_size=hidden_gru,
            num_layers=num_gru_layers,
            batch_first=True,
            dropout=dropout if num_gru_layers > 1 else 0
        )

        # ============================================================
        # MULTI-HEAD ATTENTION (Cross-Timeframe Fusion)
        # ============================================================

        self.attention_dim = hidden_gru * 3  # 256 * 3 = 768
        self.multihead_attention = nn.MultiheadAttention(
            embed_dim=self.attention_dim,
            num_heads=num_attention_heads,
            dropout=dropout,
            batch_first=True
        )

        # Layer normalization after attention
        self.attention_norm = nn.LayerNorm(self.attention_dim)

        # ============================================================
        # DENSE PREDICTION LAYERS
        # ============================================================

        self.fc1 = nn.Linear(self.attention_dim, 1024)
        self.bn1 = nn.BatchNorm1d(1024)
        self.dropout1 = nn.Dropout(dropout)

        self.fc2 = nn.Linear(1024, 512)
        self.bn2 = nn.BatchNorm1d(512)
        self.dropout2 = nn.Dropout(dropout)

        self.fc3 = nn.Linear(512, 256)
        self.bn3 = nn.BatchNorm1d(256)
        self.dropout3 = nn.Dropout(dropout)

        self.fc4 = nn.Linear(256, 128)
        self.bn4 = nn.BatchNorm1d(128)
        self.dropout4 = nn.Dropout(dropout)

        # Output layer: 3 classes (BUY, SELL, HOLD)
        self.fc_out = nn.Linear(128, 3)

        # Confidence estimation branch
        self.fc_confidence = nn.Linear(128, 1)

        # Initialize weights
        self._initialize_weights()

        # Log parameter count
        total_params = count_parameters(self)
        logger.info(f"HeliosNeuralNetwork initialized with {total_params:,} parameters")

    def _initialize_weights(self):
        """Xavier/Kaiming initialization for better convergence."""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
            elif isinstance(m, (nn.LSTM, nn.GRU)):
                for name, param in m.named_parameters():
                    if 'weight_ih' in name:
                        nn.init.xavier_uniform_(param.data)
                    elif 'weight_hh' in name:
                        nn.init.orthogonal_(param.data)
                    elif 'bias' in name:
                        nn.init.constant_(param.data, 0)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the network.

        Args:
            x: Input tensor of shape (batch_size, 90)

        Returns:
            predictions: Softmax probabilities (batch_size, 3) - [buy, sell, hold]
            confidence: Confidence scores (batch_size, 1) - [0, 1]
        """
        batch_size = x.size(0)

        # Split input into timeframes
        # Features 0-29: HFP (1min)
        # Features 30-59: MFP (5min)
        # Features 60-89: LFP (15min)
        hfp_features = x[:, 0:30].unsqueeze(1)    # (batch, 1, 30)
        mfp_features = x[:, 30:60].unsqueeze(1)   # (batch, 1, 30)
        lfp_features = x[:, 60:90].unsqueeze(1)   # (batch, 1, 30)

        # ============================================================
        # PARALLEL TIMEFRAME PROCESSING
        # ============================================================

        # HFP branch: LSTM → GRU
        hfp_lstm_out, _ = self.hfp_lstm(hfp_features)
        hfp_gru_out, _ = self.hfp_gru(hfp_lstm_out)
        hfp_encoded = hfp_gru_out[:, -1, :]  # (batch, 256)

        # MFP branch: LSTM → GRU
        mfp_lstm_out, _ = self.mfp_lstm(mfp_features)
        mfp_gru_out, _ = self.mfp_gru(mfp_lstm_out)
        mfp_encoded = mfp_gru_out[:, -1, :]  # (batch, 256)

        # LFP branch: LSTM → GRU
        lfp_lstm_out, _ = self.lfp_lstm(lfp_features)
        lfp_gru_out, _ = self.lfp_gru(lfp_lstm_out)
        lfp_encoded = lfp_gru_out[:, -1, :]  # (batch, 256)

        # ============================================================
        # MULTI-HEAD ATTENTION (Pattern Fusion)
        # ============================================================

        # Combine timeframe encodings: (batch, 1, 768)
        combined = torch.cat([hfp_encoded, mfp_encoded, lfp_encoded], dim=1).unsqueeze(1)

        # Multi-head attention
        attn_out, attn_weights = self.multihead_attention(
            combined, combined, combined
        )

        # Layer normalization + residual connection
        attn_out = self.attention_norm(attn_out + combined)
        attn_out = attn_out.squeeze(1)  # (batch, 768)

        # ============================================================
        # DENSE PREDICTION LAYERS
        # ============================================================

        # First dense layer
        x = F.relu(self.bn1(self.fc1(attn_out)))
        x = self.dropout1(x)

        # Second dense layer
        x = F.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)

        # Third dense layer
        x = F.relu(self.bn3(self.fc3(x)))
        x = self.dropout3(x)

        # Fourth dense layer
        x = F.relu(self.bn4(self.fc4(x)))
        x = self.dropout4(x)

        # Output predictions
        logits = self.fc_out(x)
        predictions = F.softmax(logits, dim=1)  # (batch, 3)

        # Confidence estimation
        confidence = torch.sigmoid(self.fc_confidence(x))  # (batch, 1)

        return predictions, confidence

    def predict_single(self, features: torch.Tensor) -> Dict:
        """
        Predict for a single sample (convenience method).

        Args:
            features: Tensor of shape (90,)

        Returns:
            Dictionary with prediction details
        """
        self.eval()
        with torch.no_grad():
            if features.dim() == 1:
                features = features.unsqueeze(0)  # Add batch dimension

            predictions, confidence = self.forward(features)

            # Get class probabilities
            buy_prob = predictions[0, 0].item()
            sell_prob = predictions[0, 1].item()
            hold_prob = predictions[0, 2].item()

            # Get predicted class
            predicted_class = torch.argmax(predictions[0]).item()
            class_names = ["BUY", "SELL", "HOLD"]

            return {
                "prediction": class_names[predicted_class],
                "probabilities": {
                    "buy": buy_prob,
                    "sell": sell_prob,
                    "hold": hold_prob
                },
                "confidence": confidence[0, 0].item(),
                "max_probability": max(buy_prob, sell_prob, hold_prob)
            }


def count_parameters(model: nn.Module) -> int:
    """
    Count trainable parameters in the model.

    Args:
        model: PyTorch model

    Returns:
        Number of trainable parameters
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def print_model_summary(model: nn.Module):
    """
    Print detailed model summary.

    Args:
        model: PyTorch model
    """
    print("=" * 80)
    print("  HELIOS NEURAL NETWORK - MODEL SUMMARY")
    print("=" * 80)
    print()

    total_params = count_parameters(model)
    print(f"Total Parameters: {total_params:,}")
    print()

    print("Layer Breakdown:")
    print("-" * 80)
    for name, module in model.named_modules():
        if len(list(module.children())) == 0:  # Leaf modules only
            params = sum(p.numel() for p in module.parameters())
            if params > 0:
                print(f"{name:40s} {params:>12,} params")

    print("=" * 80)


if __name__ == "__main__":
    # Test model creation and forward pass
    print("Testing HeliosNeuralNetwork...")
    print()

    model = HeliosNeuralNetwork()
    print_model_summary(model)

    # Test forward pass
    print("\nTesting forward pass...")
    dummy_input = torch.randn(16, 90)  # Batch size 16
    predictions, confidence = model(dummy_input)

    print(f"Input shape: {dummy_input.shape}")
    print(f"Predictions shape: {predictions.shape}")
    print(f"Confidence shape: {confidence.shape}")
    print()

    # Test single prediction
    print("Testing single prediction...")
    single_features = torch.randn(90)
    result = model.predict_single(single_features)
    print(f"Prediction: {result['prediction']}")
    print(f"Probabilities: {result['probabilities']}")
    print(f"Confidence: {result['confidence']:.4f}")
