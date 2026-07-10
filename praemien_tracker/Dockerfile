ARG BUILD_FROM
FROM $BUILD_FROM

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
