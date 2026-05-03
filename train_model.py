# -*- coding: utf-8 -*-
import json
import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
import os
import django


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DigitalCampus.settings')
django.setup()

from chatbot.models import IntentResponse

# Load dataset
with open('intents.json', encoding='utf-8') as f:
    data = json.load(f)

texts = []
intents = []
responses_dict = {}

for intent_data in data['intents']:
    intent = intent_data['intent']
    responses_dict[intent] = intent_data['responses'][0]  # use first response
    for pattern in intent_data['patterns']:
        texts.append(pattern)
        intents.append(intent)

# Add fallback pattern (empty) – not used in training but we'll keep the response
if 'fallback' not in responses_dict:
    responses_dict['fallback'] = "I'm sorry, I didn't understand. Could you rephrase?"

# Train pipeline
vectorizer = TfidfVectorizer(ngram_range=(1,2), stop_words='english')
classifier = LogisticRegression(max_iter=1000, class_weight='balanced')
pipeline = make_pipeline(vectorizer, classifier)
pipeline.fit(texts, intents)

# Save model
os.makedirs('ml_models', exist_ok=True)
joblib.dump(pipeline, 'ml_models/intent_pipeline.joblib')

# Save responses to DB (clear existing first)
IntentResponse.objects.all().delete()
for intent, response in responses_dict.items():
    IntentResponse.objects.create(intent=intent, response_text=response)

print("Training complete. Model and responses saved.")