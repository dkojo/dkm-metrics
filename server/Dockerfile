FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY dkm_server ./dkm_server
RUN pip install --no-cache-dir .
ENV DKM_DATABASE_URL=sqlite:////data/dkm.db
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "dkm_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
