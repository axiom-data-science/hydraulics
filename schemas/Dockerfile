FROM python:3.8.3-slim-buster

RUN apt-get update && apt-get install -y curl
RUN mkdir /app
COPY . /app
WORKDIR /app

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "./update_schemas.py"]