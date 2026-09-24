#!/usr/bin/env bash
# Установка для Linux
set -e
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
echo "Готово! Запуск: ./run.sh"
