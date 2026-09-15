FROM python:3.14-slim AS build

WORKDIR /app

COPY src/requirements.txt ./
COPY src/customer .

RUN pip3 install -r requirements.txt

CMD [ "python3 main.py"]
