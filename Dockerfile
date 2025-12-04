FROM python:3.10

# --- Copy keadm binary into image ---
COPY keadm /usr/local/bin/keadm
RUN chmod +x /usr/local/bin/keadm

# install python
RUN pip install flask kubernetes

COPY app.py /app/app.py
WORKDIR /app
CMD ["python3", "app.py"]
