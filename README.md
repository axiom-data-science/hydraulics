# Hydraulics

A collection of applications to exemplify the ingestion of data into Kafka, perform analysis using stream processing, and provide access to processed streamed data via REST API.

This specific application is setup to ingest data from multiple IFCB instruments, perform analysis to classify the phytoplankton species, estimate biovolume and carbon content, then make the data available via a REST API.


## Components and usage
---
1. [Kafka](#kafka)
2. [Avro Schema](#avro-schema)
3. [Postgres](#postgres)
4. [JDBC Sink Connector](#jdbc-sink-connector)
5. [PostgREST](#postgrest)
6. [IFCB Stream App](#ifcb-stream-app)
7. [Tensorflow Serving](#tensorflow-serving)
8. [Ingest Script](#ingest-script)

### Kafka

In this example, data is ingested from *ifcb-dashboards* into Kafka, but can be ingested from anywhere.

Start local instance of development version of Kafka.

On Linux:
```shell
$ docker run --rm -d --net host \
    --name kafka \
    landoop/fast-data-dev:latest
```

On macOS/Windows:
```shell
$ docker run --rm -d \
    -p 9581-9584:9581-9584 \
    -p 8081-8083:8081-8083 \
    -p 9092:9092 \
    -p 2181:2181 \
    -p 3030:3030 \
    -e ADV_HOST=localhost \
    landoop/fast-data-dev:latest
```

### Avro Schema

Data ingest into Kafka does not use a schema for the topic because [Faust](https://faust.readthedocs.io/), the stream processing library used here, does not provide first-class Avro support and doing including support adds distracting complexity to this simple example. However, a schema must be used for topics that use the Kafka JDBC sink to persist data (`ifcb-stat-key.avsc` and `ifcb-stat-value.avsc` in this case).

After Kafka is up-and-running, update the Kafka schema registry to include the schemas used for statistics about the ingested IFCB data.

Build and use the Docker container for the script to update the schema.
Linux
```shell
$ docker build -t update-schemas schemas
$ docker run --net host update-schemas:latest all http://localhost:8081
```

macOS/Windows
```shell
$ docker build -t update-schemas schemas
$ docker run update-schemas:latest all http://host.docker.internal:8081
```

### Postgres

Data in the *ifcb-stats* topic is persisted to a Postgres database.

Build and run the database.
```shell
$ docker build -t kafka-messages-db db/db
$ docker run --rm -d --name kafka-db \
    -p 5441:5432 \
    -e POSTGRES_USER=kafka \
    -e POSTGRES_PASSWORD=somepassword \
    -e POSTGRES_DB=topics \
    kafka-messages-db:latest
```

Note this will not persist the data between container restarts.  To do so, one must provide
a volume on the host.

### JDBC Sink Connector

A JDBC sink connector is used to connect Kafka to the Postgres database.

Start the JDBC connector.

Linux
```shell
$ docker run -d --name kafka-sink-connector \
    --net host \
    -v $(pwd)/db/connector:/tmp/ \
    confluentinc/cp-kafka-connect:4.0.0 \
    /tmp/startup.sh
```

Something like below should work on macOS/Windows, but it is not verified.
```shell
$ docker run -d --name kafka-sink-connector \
    -e ADV_HOST=localhost \
    -v $(pwd)/db/connector:/tmp/ \
    confluentinc/cp-kafka-connect:4.0.0 \
    /tmp/startup.sh
```

### PostGREST API

Provides a REST API for ingested topics.

```
$ docker run -d --name postgrest \
    --net host \
    -v $(pwd)/db/api/postgrest.conf:/etc/postgrest.conf \
    postgrest/postgrest
```

Web application available at http://localhost:3000.  The query API documentation is available at https://postgrest.org/en/v5.0/api.html.

### IFCB Stream App

The IFCB stream app listens for new messages on the ifcb-image Kafka topic.  When a new image
is published to the topic, the specimen in the image is classified using a CNN based model deployed on [Tensorflow Serving](#tensorflow-serving), biovolume and carbon content are estimated, and summary of the satistics are published to a Kafka topic.

Build Docker image of app and deploy a single worker.
```shell
$ docker build -t ifcb-stream-app -f hydraulics/ifcb/Dockerfile.app  hydraulics
$ docker run -d --rm --net host ifcb-stream-app
```

A status page is available at http://localhost:6066/.

### Tensorflow Serving

Tensorflow based classification models were trained on labeled data collected in the Eastern Pacific Ocean by the [Kudela Lab (UCSC)](http://oceandatacenter.ucsc.edu/home/).  Generally, most CNN models trained on this dataset had high accuracy on validation test (~0.98+).

Two of the many models developed are deployed via Tensorflow Serving:
- A Densenet based model: http://stage-ifcb-model.srv.axds.co/v1/models/ifcb-densenet:predict
- An Xception based model:http://stage-ifcb-model.srv.axds.co/v1/models/ifcb-xception:predict

See cnn_models/{ifcb_densenet121.py,ifcb_xception.py} for details about the model and training setup that
was used for these models.


### Ingestion Script

An script to ingest IFCB image data via the `ifcb-dashboard` is provided in `hydraulics/ifcb/image_ingestory.py`.

To run in Docker:

```bash
$ docker build -t ifcb-ingestor hydraulics/ifcb -f hydraulics/ifcb/Dockerfile.ingestor
$ docker run ifcb-ingestor:latest publish-feed-images <ifcb-dashboard> <kafka-image-topic> <kafka-broker> --nbins 1
```

A specific example to ingest the most recent bin from IFCB113 to the local Kafka topic *ifcb-images.
```bash
$ docker run --net host ifcb-ingestor:latest publish-feed-images http://128.114.25.154:8888/IFCB113/ ifcb-images localhost:9092 --nbins 1
```
