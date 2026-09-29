FROM python:3.12-slim
WORKDIR /app
COPY requirements-vector.txt /app/
RUN pip install --no-cache-dir -r requirements-vector.txt
COPY . /app
RUN useradd --uid 10001 --create-home campus && mkdir -p /app/data && chown -R campus:campus /app
USER campus
ENV PYTHONUNBUFFERED=1 CAMPUS_HOST=0.0.0.0
EXPOSE 8765
CMD ["python", "run.py"]
