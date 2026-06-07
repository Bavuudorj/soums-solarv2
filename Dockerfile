# Сумдын нарны эрчим хүчний хангамжийн төлөвлөлтийн Streamlit апп
# Python 3.12 (тогтвортой wheel-үүдтэй; 3.14 биш — зарим сан 3.14 Linux wheel-гүй)
FROM python:3.12-slim

# Орчны тохиргоо
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app

# Хамаарлыг эхэлж суулгах (давхаргын кэш ашиглах)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Аппын код + өгөгдөл
COPY . .

# Streamlit порт
EXPOSE 8501

# Эрүүл мэндийн шалгалт
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health').status==200 else 1)"

# Аппыг асаах
ENTRYPOINT ["streamlit", "run", "app.py", \
            "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
