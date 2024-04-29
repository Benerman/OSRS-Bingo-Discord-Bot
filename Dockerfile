FROM python:3.10-bullseye
COPY requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt
COPY OSRS-Bingo-Bingo-Bot/OSRS-Bingo-Discord-Bot/ .
RUN mkdir -p /app/images
CMD ["python3", "bot.py"]

