FROM python:3-alpine

ADD requirements.txt .
RUN python -m pip install -r requirements.txt

COPY static static
COPY app app
COPY main.py main.py

CMD ["python", "main.py"]
