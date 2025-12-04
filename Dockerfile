FROM python:3.10-slim

# Install system dependencies needed for kubernetes client
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*


# Copy keadm binary into container



# Install python dependencies
RUN pip install flask kubernetes

# Copy master app files
WORKDIR /app
COPY app.py /app/app.py

CMD ["python3", "app.py"]
