# ai/services/anomalies.py
from sklearn.ensemble import IsolationForest
def train_iso(X):  # X: engineered features per transaction
    clf = IsolationForest(contamination=0.01, random_state=42).fit(X)
    scores = clf.decision_function(X)
    return clf, scores