FROM public.ecr.aws/lambda/python:3.12

# Copy requirements
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy app
COPY app/ ${LAMBDA_TASK_ROOT}/app/
COPY config/ /opt/config/

# Copy Lambda handler
COPY app/lambda_handler.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to the handler
CMD ["lambda_handler.lambda_handler"]
