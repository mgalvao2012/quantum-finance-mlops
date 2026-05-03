#!/usr/bin/env bash
set -euo pipefail # -e: exit on error, -u: treat unset variables as error, -o pipefail: catch errors in pipelines

# Configurar ambiente Python e instala as dependências
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Gerar arquivo Parquet com os dados brutos (necessário para o feast apply inferir o schema)
python src/data/ingest.py

# Inicializar o Feast feature store
cd feature_repo && feast apply && cd ..

# Executar o treinamento
python src/model/train.py

echo "Setup concluído. O ambiente está pronto para uso."
