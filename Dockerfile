FROM python:3.10-slim

# Install system dependencies required for kubernetes client
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the keadm binary into container
COPY keadm /usr/local/bin/keadm
RUN chmod +x /usr/local/bin/keadm

# Install python libraries
RUN pip install flask kubernetes

# Copy application
WORKDIR /app
COPY app.py /app/app.py

# Expose port
EXPOSE 5000

CMD ["python3", "app.py"]
