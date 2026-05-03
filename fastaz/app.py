from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI()

# Load the trained model
try:
    model = joblib.load("xgboost_model.joblib")
except FileNotFoundError:
    print(
        "Model file not found. Please run train.py first to train and save the model."
    )
    model = None


class PredictionRequest(BaseModel):
    features: list[float]


@app.post("/predict/")
async def predict(request: PredictionRequest):
    if model is None:
        return {"error": "Model not loaded. Please train the model first."}

    # Convert features to numpy array and reshape for prediction
    input_features = np.array(request.features).reshape(1, -1)

    prediction = model.predict(input_features).tolist()
    prediction_proba = model.predict_proba(input_features).tolist()

    return {"prediction": prediction, "prediction_proba": prediction_proba}


@app.get("/health")
async def health_check():
    return {"status": "ok", "model_loaded": model is not None}
