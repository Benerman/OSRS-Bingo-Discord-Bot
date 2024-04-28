FROM python:3.10-bullseye
COPY requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt
COPY bot.py config.py token.json settings.json credentials.json ./
RUN mkdir -p /app/images
COPY ./images /app/images
CMD ["python3", "bot.py"]

