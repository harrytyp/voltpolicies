FROM python:3.12-slim

WORKDIR /app

# Install git for cloning the repo
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY app.py .

# Expose the MCP SSE port
ENV PORT=7860
EXPOSE 7860

# Start the server
CMD ["python", "app.py"]
