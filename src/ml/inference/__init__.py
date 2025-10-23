"""
Inference engine for Helios V3 - AutoGluon Ensemble ONLY.

IMPORTANT: Legacy prediction services (Tier2PredictionService, HeliosPredictor)
have been deprecated and removed. The system now uses ONLY AutoGluon for predictions.
"""

from src.ml.inference.ensemble_prediction_service import EnsemblePredictionService

__all__ = ["EnsemblePredictionService"]
