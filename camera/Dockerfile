FROM python:3.12-slim
WORKDIR /app
# Phase 2 : docker compose build --build-arg INSTALL_YOLO=true (télécharge torch, ~2 Go)
ARG INSTALL_YOLO=false
COPY requirements.txt requirements-yolo.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_YOLO" = "true" ]; then \
         pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
         && pip install --no-cache-dir -r requirements-yolo.txt; \
       fi
COPY *.py ./
CMD ["python", "-u", "camera.py"]
