FROM python:3.7-slim-buster
RUN apt-get -y update && \
    apt-get install -y \
    build-essential \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    librocksdb-dev \
    libsnappy-dev \
    liblz4-dev

COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
WORKDIR /app/ifcb

CMD faust -A classifier worker -l info
