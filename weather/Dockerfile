FROM python:3.12-slim
WORKDIR /app
COPY weather/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY weather ./weather
COPY ml/fwi.py ./ml/fwi.py
COPY dashboard/daily_data.py dashboard/daily_payload.py ./dashboard/
ENV PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
CMD ["python", "-m", "weather.collector", "--risk-data", "/risk", "--data", "/weather"]
