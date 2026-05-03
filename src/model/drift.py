import sys
import os
import pandas as pd
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DRIFT_REPORTS_PATH

_default_report_path = os.path.join(DRIFT_REPORTS_PATH, "drift_report.html")

def detect_data_drift(
    reference_data: pd.DataFrame,
    current_data: pd.DataFrame,
    report_path: str = _default_report_path,
) -> bool:
    """
    Compara o lote atual de dados com a base de referência para detectar drift.
    Gera um relatório visual em HTML na pasta apropriada.
    """
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    drift_report = Report(metrics=[DataDriftPreset()])

    # Executa a comparação
    drift_report.run(reference_data=reference_data, current_data=current_data)

    # Salva o artefato visual
    drift_report.save_html(report_path)

    # Extrai o resultado booleano (True se houve drift significativo no dataset como um todo)
    result_dict = drift_report.as_dict()
    dataset_drift = result_dict["metrics"][0]["result"]["dataset_drift"]

    return dataset_drift
