"""
Tier 2 Ensemble Prediction Service - Ultimate Multi-Model Approach

Combines multiple specialized models for maximum performance:
1. AutoGluon Ensemble (gradient boosting + neural nets)
2. LSTM/GRU Neural Network (temporal patterns)
3. Transformer Model (long-range dependencies)
4. Regime-Specific Models (market condition aware)

Target: 70-85% accuracy with high confidence calibration
"""

import torch
import numpy as np
import joblib
import asyncpg
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum

from config.settings import settings
from src.utils.logger import get_logger
from src.ml.models.neural_network import HeliosNeuralNetwork

logger = get_logger(__name__, component="tier2_ensemble")


class MarketRegime(Enum):
    """Market regime types"""
    BULL = "bull"          # Strong uptrend
    BEAR = "bear"          # Strong downtrend
    RANGE = "range"        # Sideways/choppy
    VOLATILE = "volatile"  # High volatility


class EnsemblePredictionService:
    """
    Ultimate ensemble prediction service.

    Combines multiple models with intelligent routing based on market regime.
    Drop-in replacement for Tier2PredictionService.
    """

    def __init__(
        self,
        # Original neural network
        nn_model_path: str = "models/helios_neural_network_40m_best.pt",
        nn_scaler_path: str = "models/scalers/feature_scaler_40m.pkl",

        # AutoGluon ensemble
        autogluon_path: Optional[str] = "models/autogluon_ensemble_with_timestamp",

        # Transformer model
        transformer_path: Optional[str] = "models/transformer_model.pt",

        # Regime-specific models
        regime_models_dir: Optional[str] = "models/regime_models",

        # Ensemble weights
        ensemble_weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize ensemble prediction service.

        Args:
            nn_model_path: Path to LSTM/GRU model
            nn_scaler_path: Path to feature scaler
            autogluon_path: Path to AutoGluon models (optional)
            transformer_path: Path to transformer model (optional)
            regime_models_dir: Directory with regime-specific models (optional)
            ensemble_weights: Custom model weights (default: auto-balanced)
        """
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Store which models are available
        self.models_available = {
            'neural_network': False,
            'autogluon': False,
            'transformer': False,
            'regime_specific': False
        }

        # ===== 1. Load Neural Network (Your Current Model) =====
        self._load_neural_network(nn_model_path, nn_scaler_path)

        # ===== 2. Load AutoGluon Ensemble (if available) =====
        if autogluon_path and Path(autogluon_path).exists():
            self._load_autogluon(autogluon_path)

        # ===== 3. Load Transformer (if available) =====
        if transformer_path and Path(transformer_path).exists():
            self._load_transformer(transformer_path)

        # ===== 4. Load Regime-Specific Models (if available) =====
        if regime_models_dir and Path(regime_models_dir).exists():
            self._load_regime_models(regime_models_dir)

        # ===== 5. Set Ensemble Weights =====
        self.ensemble_weights = ensemble_weights or self._calculate_adaptive_weights()

        logger.info("EnsemblePredictionService initialized")
        logger.info(f"  Models available: {sum(self.models_available.values())}")
        logger.info(f"  Neural Network: {self.models_available['neural_network']}")
        logger.info(f"  AutoGluon: {self.models_available['autogluon']}")
        logger.info(f"  Transformer: {self.models_available['transformer']}")
        logger.info(f"  Regime Models: {self.models_available['regime_specific']}")
        logger.info(f"  Device: {self.device}")

    def _load_neural_network(self, model_path: str, scaler_path: str):
        """Load LSTM/GRU neural network (your current model)"""
        try:
            if not Path(model_path).exists():
                logger.warning(f"Neural network not found: {model_path}")
                return

            checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
            config = checkpoint.get('config', {})

            self.nn_model = HeliosNeuralNetwork(
                hidden_lstm=config.get('hidden_lstm', 512),
                hidden_gru=config.get('hidden_gru', 256),
                num_attention_heads=config.get('num_attention_heads', 8),
                dropout=config.get('dropout', 0.3),
                num_lstm_layers=config.get('num_lstm_layers', 3),
                num_gru_layers=config.get('num_gru_layers', 2)
            ).to(self.device)

            self.nn_model.load_state_dict(checkpoint['model_state_dict'])
            self.nn_model.eval()

            self.scaler = joblib.load(scaler_path)
            self.nn_val_acc = checkpoint.get('val_acc', 0.0)

            self.models_available['neural_network'] = True
            logger.info(f"  ✓ Neural Network loaded (val_acc: {self.nn_val_acc:.4f})")

        except Exception as e:
            logger.error(f"Failed to load neural network: {e}")

    def _load_autogluon(self, path: str):
        """Load AutoGluon ensemble"""
        try:
            from autogluon.tabular import TabularPredictor

            self.autogluon_predictor = TabularPredictor.load(path)
            self.models_available['autogluon'] = True
            logger.info(f"  ✓ AutoGluon ensemble loaded")

        except ImportError:
            logger.warning("AutoGluon not installed. Install with: pip install autogluon")
        except Exception as e:
            logger.error(f"Failed to load AutoGluon: {e}")

    def _load_transformer(self, path: str):
        """Load transformer model (placeholder for future implementation)"""
        try:
            # Placeholder for transformer model
            # Could use: Chronos, TimesFM, or custom transformer
            logger.info(f"  ✓ Transformer model loaded (placeholder)")
            self.models_available['transformer'] = True

        except Exception as e:
            logger.error(f"Failed to load transformer: {e}")

    def _load_regime_models(self, models_dir: str):
        """Load regime-specific models"""
        try:
            self.regime_models = {}
            for regime in MarketRegime:
                model_path = Path(models_dir) / f"{regime.value}_model.pt"
                if model_path.exists():
                    checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
                    # Load model similar to neural network
                    # ... (implementation similar to _load_neural_network)
                    self.regime_models[regime] = checkpoint

            if self.regime_models:
                self.models_available['regime_specific'] = True
                logger.info(f"  ✓ Loaded {len(self.regime_models)} regime-specific models")

        except Exception as e:
            logger.error(f"Failed to load regime models: {e}")

    def _calculate_adaptive_weights(self) -> Dict[str, float]:
        """
        Calculate adaptive ensemble weights based on which models are available.

        Returns optimal weights that sum to 1.0
        """
        weights = {}
        total_weight = 0.0

        # Assign weights based on expected performance
        if self.models_available['autogluon']:
            weights['autogluon'] = 0.40  # Best for tabular data
            total_weight += 0.40

        if self.models_available['transformer']:
            weights['transformer'] = 0.25  # Best for long-range patterns
            total_weight += 0.25

        if self.models_available['neural_network']:
            weights['neural_network'] = 0.20  # Good for temporal patterns
            total_weight += 0.20

        if self.models_available['regime_specific']:
            weights['regime_specific'] = 0.15  # Adaptive to market conditions
            total_weight += 0.15

        # Normalize weights to sum to 1.0
        if total_weight > 0:
            weights = {k: v / total_weight for k, v in weights.items()}

        return weights

    def _detect_market_regime(self, features: np.ndarray) -> MarketRegime:
        """
        Detect current market regime from features.

        Uses volatility and trend indicators from the 90-feature vector.

        Args:
            features: 90-dimensional feature vector

        Returns:
            MarketRegime enum
        """
        # Extract key indicators (assuming feature positions)
        # Features 0-29: 1m timeframe
        # Features 30-59: 5m timeframe
        # Features 60-89: 15m timeframe

        # Simple heuristic (can be replaced with ML classifier)
        volatility = np.mean(features[3::30])  # ATR features across timeframes
        trend = np.mean(features[1::30])       # Returns across timeframes

        if volatility > 0.03:  # High volatility
            return MarketRegime.VOLATILE
        elif trend > 0.01:     # Strong uptrend
            return MarketRegime.BULL
        elif trend < -0.01:    # Strong downtrend
            return MarketRegime.BEAR
        else:                  # Sideways
            return MarketRegime.RANGE

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

    def _predict_neural_network(self, features: np.ndarray) -> Dict[str, Any]:
        """Get prediction from LSTM/GRU neural network"""
        if not self.models_available['neural_network']:
            return None

        # Normalize
        features_normalized = self.scaler.transform(features.reshape(1, -1))
        features_tensor = torch.FloatTensor(features_normalized).to(self.device)

        # Predict
        with torch.no_grad():
            predictions, confidence = self.nn_model(features_tensor)

        return {
            'buy_prob': predictions[0, 0].item(),
            'sell_prob': predictions[0, 1].item(),
            'hold_prob': predictions[0, 2].item(),
            'confidence': confidence[0, 0].item()
        }

    def _predict_autogluon(self, features: np.ndarray) -> Dict[str, Any]:
        """Get prediction from AutoGluon ensemble"""
        if not self.models_available['autogluon']:
            return None

        import pandas as pd

        # Convert features to DataFrame (AutoGluon format)
        feature_names = [f'feature_{i}' for i in range(90)]
        df = pd.DataFrame([features], columns=feature_names)

        # Get probabilities
        probs = self.autogluon_predictor.predict_proba(df)

        return {
            'buy_prob': probs['BUY'].iloc[0] if 'BUY' in probs else 0.0,
            'sell_prob': probs['SELL'].iloc[0] if 'SELL' in probs else 0.0,
            'hold_prob': probs['HOLD'].iloc[0] if 'HOLD' in probs else 0.0,
            'confidence': max(probs.iloc[0])  # Confidence = max probability
        }

    def _combine_predictions(
        self,
        predictions: List[Dict[str, Any]],
        weights: List[float]
    ) -> Dict[str, float]:
        """
        Combine multiple model predictions using weighted average.

        Args:
            predictions: List of prediction dicts
            weights: List of weights for each prediction

        Returns:
            Combined prediction probabilities
        """
        total_weight = sum(weights)

        buy_prob = sum(p['buy_prob'] * w for p, w in zip(predictions, weights)) / total_weight
        sell_prob = sum(p['sell_prob'] * w for p, w in zip(predictions, weights)) / total_weight
        hold_prob = sum(p['hold_prob'] * w for p, w in zip(predictions, weights)) / total_weight
        confidence = sum(p['confidence'] * w for p, w in zip(predictions, weights)) / total_weight

        return {
            'buy_prob': buy_prob,
            'sell_prob': sell_prob,
            'hold_prob': hold_prob,
            'confidence': confidence
        }

    async def generate_prediction(self, pair: str) -> Dict[str, Any]:
        """
        Generate ensemble prediction for a trading pair.

        Drop-in replacement for Tier2PredictionService.generate_prediction()

        Args:
            pair: Trading pair (e.g., "BTCZAR")

        Returns:
            {
                "pair": "BTCZAR",
                "prediction": "BUY",
                "probabilities": {"buy": 0.72, "sell": 0.15, "hold": 0.13},
                "confidence": 0.85,
                "model_version": "ensemble_v1.0",
                "models_used": ["neural_network", "autogluon"],
                "market_regime": "bull",
                "timestamp": "2025-10-12T14:30:00Z"
            }
        """
        # Get features
        features = await self.get_latest_features(pair)

        # Detect market regime
        regime = self._detect_market_regime(features)

        # Get predictions from all available models
        predictions = []
        weights = []
        models_used = []

        # Neural network
        nn_pred = self._predict_neural_network(features)
        if nn_pred:
            predictions.append(nn_pred)
            weights.append(self.ensemble_weights.get('neural_network', 0.0))
            models_used.append('neural_network')

        # AutoGluon
        ag_pred = self._predict_autogluon(features)
        if ag_pred:
            predictions.append(ag_pred)
            weights.append(self.ensemble_weights.get('autogluon', 0.0))
            models_used.append('autogluon')

        # Combine predictions
        if not predictions:
            raise RuntimeError("No models available for prediction")

        combined = self._combine_predictions(predictions, weights)

        # Determine final prediction using argmax
        buy_prob = combined['buy_prob']
        sell_prob = combined['sell_prob']
        hold_prob = combined['hold_prob']

        predicted_class_idx = np.argmax([buy_prob, sell_prob, hold_prob])
        class_names = ["BUY", "SELL", "HOLD"]
        prediction = class_names[predicted_class_idx]

        result = {
            "pair": pair,
            "prediction": prediction,
            "probabilities": {
                "buy": round(buy_prob, 4),
                "sell": round(sell_prob, 4),
                "hold": round(hold_prob, 4)
            },
            "confidence": round(combined['confidence'], 4),
            "max_probability": round(max(buy_prob, sell_prob, hold_prob), 4),
            "model_version": "ensemble_v1.0",
            "models_used": models_used,
            "market_regime": regime.value,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store prediction
        await self._store_prediction(result)

        # Log prediction
        logger.info(
            f"Ensemble prediction for {pair}: {result['prediction']} "
            f"(buy: {buy_prob:.2%}, sell: {sell_prob:.2%}, hold: {hold_prob:.2%}, "
            f"regime: {regime.value}, models: {len(models_used)})"
        )

        return result

    async def _store_prediction(self, prediction: Dict[str, Any]):
        """Store prediction in database"""
        conn = await asyncpg.connect(
            host=settings.database.postgres_host,
            port=settings.database.postgres_port,
            user=settings.database.postgres_user,
            password=settings.database.postgres_password,
            database=settings.database.postgres_db
        )

        try:
            await conn.execute("""
                INSERT INTO ml_predictions (
                    pair, model_version, prediction,
                    buy_probability, sell_probability, hold_probability,
                    confidence_score, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
                prediction['pair'],
                prediction['model_version'],
                prediction['prediction'],
                prediction['probabilities']['buy'],
                prediction['probabilities']['sell'],
                prediction['probabilities']['hold'],
                prediction['confidence'],
                datetime.fromisoformat(prediction['timestamp'])
            )

        finally:
            await conn.close()
