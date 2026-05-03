import xgboost as xgb
import numpy as np
import pandas as pd
import joblib

def train_and_save_model(n_samples=1000, n_features=10, filename="xgboost_model.joblib"):
    """
    Generates mock data, trains an XGBoost model, and saves it.
    """
    print("Generating mock data...")
    X = np.random.rand(n_samples, n_features)
    y = np.random.randint(0, 2, n_samples) # Binary classification target

    print("Training XGBoost model...")
    model = xgb.XGBClassifier(objective='binary:logistic', eval_metric='logloss')
    model.fit(X, y)

    print(f"Saving model to {filename}...")
    joblib.dump(model, filename)
    print("Model saved successfully.")

if __name__ == "__main__":
    train_and_save_model()