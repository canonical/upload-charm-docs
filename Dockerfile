FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends git=1:2.30.*

RUN mkdir /usr/src/app
WORKDIR /usr/src/app
COPY requirements.txt /usr/src/app
RUN pip install --no-cache-dir -r requirements.txt

COPY . /usr/src/app

ENV PYTHONPATH /usr/src/app
CMD ["/usr/src/app/main.py"]
