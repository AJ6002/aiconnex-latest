# 1. Use a standard slim python environment
FROM python:3.9-slim

# 2. Install your required ML libraries
RUN pip install scikit-learn==1.2.1 pandas numpy boto3 --no-cache-dir

# 3. Copy your train.py script into the container
COPY services/sagemaker_pipeline/src/train.py /app/train.py

# 4. Set the working directory
WORKDIR /app

# 5. Tell the container to run your script when it starts
ENTRYPOINT ["python", "train.py"]
