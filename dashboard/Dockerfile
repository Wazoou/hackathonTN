FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY timeline_component ./timeline_component
EXPOSE 8501
ENV STREAMLIT_THEME_BASE=light \
    STREAMLIT_THEME_PRIMARY_COLOR="#216e55" \
    STREAMLIT_THEME_BACKGROUND_COLOR="#f3f5f4" \
    STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR="#ffffff" \
    STREAMLIT_THEME_TEXT_COLOR="#253747"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.gatherUsageStats=false"]
