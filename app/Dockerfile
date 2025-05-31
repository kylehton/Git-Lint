# Dockerfile
FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# use uvicorn worker class since we need ASGI not WSGI
CMD ["main.handler"]
