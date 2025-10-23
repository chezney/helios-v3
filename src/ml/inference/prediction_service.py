"""
Tier 2 Prediction Service - Real-time Neural Network Inference

Generates BUY/SELL/HOLD predictions from 90-dimensional feature vectors.
Target latency: <100ms per prediction.
"""

import torch
import numpy as np
import joblib
import asyncpg
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from config.settings import settings
from src.utils.logger import get_logger
from src.ml.models.neural_network import HeliosNeuralNetwork

logger = get_logger(__name__, component="tier2_prediction")


class Tier2PredictionService:
    """
    Real-time prediction service for Helios neural network.

    Loads trained model and generates predictions from feature vectors.
    """

    def __init__(
        self,
        model_path: str = "models/helios_neural_network_40m_best.pt",
        scaler_path: str = "models/scalers/feature_scaler_40m.pkl"
    ):
        """
        Initialize prediction service.

        Args:
            model_path: Path to trained model checkpoint
            scaler_path: Path to fitted StandardScaler
        """
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load model
        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        checkpoint = torch.load(model_path, map_location=self.device)

        # Get model config from checkpoint if available
        config = checkpoint.get('config', {})

        self.model = HeliosNeuralNetwork(
            hidden_lstm=config.get('hidden_lstm', 512),
            hidden_gru=config.get('hidden_gru', 256),
            num_attention_heads=config.get('num_attention_heads', 8),
            dropout=config.get('dropout', 0.3),
            num_lstm_layers=config.get('num_lstm_layers', 3),
            num_gru_layers=config.get('num_gru_layers', 2)
        ).to(self.device)

        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()

        self.model_version = f"40m_v1.0_epoch{checkpoint.get('epoch', 0)}"
        self.val_acc = checkpoint.get('val_acc', 0.0)

        # Load scaler
        if not Path(scaler_path).exists():
            raise FileNotFoundError(f"Scaler not found: {scaler_path}")

        self.scaler = joblib.load(scaler_path)

        logger.info(f"Tier2PredictionService initialized")
        logger.info(f"  Model: {model_path}")
        logger.info(f"  Validation accuracy: {self.val_acc:.4f}")
        logger.info(f"  Device: {self.device}")

    async def get_latest_features(self, pair: str) -> np.ndarray:
        """
        Get latest 90-dimensional features from database.

        Args:
            pair: Trading pair (e.g., "BTCZAR")

        Returns:
            numpy array of shape (90,)
        """
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            # Get most recent feature vector
            row = await conn.fetchrow("""
                SELECT features_vector
                FROM engineered_features
                WHERE pair = $1
                ORDER BY computed_at DESC
                LIMIT 1
            """, pair)

            if not row:
                raise ValueError(f"No features found for {pair}")

            fv = row['features_vector']
            if isinstance(fv, str):
                fv = json.loads(fv)

            features = fv.get('features', [])

            if len(features) != 90:
                raise ValueError(f"Expected 90 features, got {len(features)}")

            return np.array(features, dtype=np.float32)

        finally:
            await conn.close()

    async def generate_prediction(self, pair: str) -> Dict[str, Any]:
        """
        Generate prediction for a trading pair.

        Args:
            pair: Trading pair (e.g., "BTCZAR")

        Returns:
            {
                "pair": "BTCZAR",
                "prediction": "BUY",
                "probabilities": {"buy": 0.72, "sell": 0.15, "hold": 0.13},
                "confidence": 0.85,
                "model_version": "40m_v1.0",
                "timestamp": "2025-10-12T14:30:00Z"
            }
        """
        # Get features
        features = await self.get_latest_features(pair)

        # Normalize
        features_normalized = self.scaler.transform(features.reshape(1, -1))
        features_tensor = torch.FloatTensor(features_normalized).to(self.device)

        # Predict
        with torch.no_grad():
            predictions, confidence = self.model(features_tensor)

        # Parse results
        buy_prob = predictions[0, 0].item()
        sell_prob = predictions[0, 1].item()
        hold_prob = predictions[0, 2].item()

        predicted_class = torch.argmax(predictions[0]).item()
        class_names = ["BUY", "SELL", "HOLD"]

        result = {
            "pair": pair,
            "prediction": class_names[predicted_class],
            "probabilities": {
                "buy": round(buy_prob, 4),
                "sell": round(sell_prob, 4),
                "hold": round(hold_prob, 4)
            },
            "confidence": round(confidence[0, 0].item(), 4),
            "max_probability": round(max(buy_prob, sell_prob, hold_prob), 4),
            "model_version": self.model_version,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store prediction in database
        await self._store_prediction(result)

        logger.info(
            f"Prediction for {pair}: {result['prediction']} "
            f"(conf={result['confidence']:.2f})"
        )

        return result

    async def _store_prediction(self, prediction: Dict[str, Any]):
        """Store prediction in database for tracking."""
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                INSERT INTO ml_predictions
                (pair, model_version, prediction, buy_probability, sell_probability,
                 hold_probability, confidence_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                prediction["pair"],
                prediction["model_version"],
                prediction["prediction"],
                prediction["probabilities"]["buy"],
                prediction["probabilities"]["sell"],
                prediction["probabilities"]["hold"],
                prediction["confidence"]
            )

        except Exception as e:
            logger.warning(f"Failed to store prediction: {e}")

        finally:
            await conn.close()
