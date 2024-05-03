FROM python:3.10-bullseye
COPY requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p /app/images
CMD ["python3", "-u", "bot.py"]

