FROM public.ecr.aws/lambda/python:3.14 AS build

WORKDIR /app

COPY src/requirements.txt ./

RUN pip3 install -r requirements.txt

COPY src/user_service .

CMD [ "user_handler.lambda_handler"]