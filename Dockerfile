# Use an official Python runtime as a parent image
FROM python:3.12-bookworm

# Set environment variables for application configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy .env file and source it for environment variables
# COPY .env /app/.env
COPY Pipfile Pipfile.lock /app/
# Set the working directory in the container
WORKDIR /app

RUN pip install --upgrade pip && \
    pip install pipenv && \
    pipenv install --deploy --ignore-pipfile --system
# Install system dependencies needed for various Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    # build-essential \
    # gcc \
    # g++ \
    libc-dev \
    libpq-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    # libopencv-dev \
    python3-opencv \
    libssl-dev \
    libgl1 \
    # curl \
    # git \
    # dos2unix \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and convert line endings if necessary
# COPY requirements.txt /app/
# RUN dos2unix /app/requirements.txt

# Create a clean requirements file with specified versions
# RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Manual installation of packages that might cause conflicts
# RUN pip install --no-cache-dir gunicorn==21.2.0
# RUN pip install --no-cache-dir uvicorn[standard]==0.30.1
# RUN pip install --no-cache-dir psycopg2-binary==2.9.10
# RUN pip install --no-cache-dir numpy==2.2.4 scipy==1.15.2 scikit-learn==1.6.1
RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
# RUN pip install --no-cache-dir opencv-python==4.11.0.86 opencv-python-headless==4.11.0.86
# RUN pip install --no-cache-dir transformers==4.50.3 sentence-transformers==4.0.1
# Add hf_xet for better Hugging Face model downloads
RUN pip install --no-cache-dir hf_xet huggingface_hub[hf_xet]

# Install remaining packages
# RUN pip install --no-cache-dir -r /app/requirements.txt

# Create a properly formatted .env file with fixed database URL
# RUN sed -i 's|DATABASE_URL=.*|DATABASE_URL=postgresql://neondb_owner:npg_DkAiXyLuRx23@ep-orange-rain-a2usbm66-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require\&options=endpoint%3Dep-orange-rain-a2usbm66|g' /app/.env

# Copy the rest of the application code into the container
COPY . /app/
# Create directories for image uploads if they don't exist
RUN mkdir -p /app/found_item_images /app/lost_item_images

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define the command to run your app using Uvicorn for ASGI support
CMD ["uvicorn", "core.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
