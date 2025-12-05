FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install flask kubernetes


WORKDIR /app
COPY app.py /app/app.py

CMD ["python3", "app.py"]
