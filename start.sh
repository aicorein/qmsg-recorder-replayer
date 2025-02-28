#!/bin/bash
cd src
unset http_proxy
unset https_proxy
unset HTTP_PROXY
unset HTTPS_PROXY
source /opt/miniconda3/etc/profile.d/conda.sh
conda activate ../.venv
python main.py
