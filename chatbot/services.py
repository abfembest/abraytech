import joblib
import numpy as np
from django.conf import settings
import os

class IntentClassifier:
    _pipeline = None

    @classmethod
    def get_pipeline(cls):
        if cls._pipeline is None:
            model_path = os.path.join(settings.BASE_DIR, 'ml_models', 'intent_pipeline.joblib')
            cls._pipeline = joblib.load(model_path)
        return cls._pipeline

    @classmethod
    def predict(cls, text, threshold=0.1):
        pipeline = cls.get_pipeline()
        probs = pipeline.predict_proba([text])[0]
        max_prob = np.max(probs)
        if max_prob < threshold:
            return 'fallback', max_prob
        intent = pipeline.classes_[np.argmax(probs)]
        return intent, max_prob